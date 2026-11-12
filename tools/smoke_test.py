"""デモモードでの動作確認（Supabase不要）。
準備:  pip install playwright && playwright install chromium
実行:  python3 tools/smoke_test.py      （リポジトリ直下で）
結果:  すべて OK と表示されれば成功。tools/shots/ に画面キャプチャを保存します。
"""
import asyncio, pathlib, shutil, sys, tempfile
from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
# config.js に本番の接続情報が入っていても、空の config.js を置いた一時コピーでデモモードとして確認する
_TMP = pathlib.Path(tempfile.mkdtemp(prefix="staff-checkin-test-"))
shutil.copy(ROOT / "index.html", _TMP / "index.html")
(_TMP / "config.js").write_text('window.APP_CONFIG = { SUPABASE_URL: "", SUPABASE_ANON_KEY: "" };', encoding="utf-8")
BASE = (_TMP / "index.html").as_uri()
SHOTS = ROOT / "tools" / "shots"
fails = []
def check(name, cond):
    print(("OK  " if cond else "NG  ") + name)
    if not cond: fails.append(name)

async def guide_finish(pg, hide):
    """使い方のスライドを最後まで「次へ」で進め、確認する"""
    while await pg.locator(".gnav [data-act=gpage]:has-text('次へ')").count():
        await pg.click(".gnav [data-act=gpage]:has-text('次へ')")
    if hide: await pg.check("#guidehide")
    await pg.click("[data-act=guideok]")

async def login(pg, now):
    await pg.goto(f"{BASE}?now={now}")
    if await pg.locator("#email").count():
        await pg.fill("#email", "me@example.com"); await pg.click("[data-act=send]")
        await pg.wait_for_selector("#name"); await pg.fill("#name", "岡山 太郎"); await pg.click("[data-act=savename]")
    if await pg.locator(".guide").count():
        await guide_finish(pg, True)
    await pg.wait_for_selector(".vsel")

async def main():
    SHOTS.mkdir(exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))

        # 使い方の案内：氏名入力後に出る → チェックなしで確認 → 再読み込みでまた出る → チェックして確認 → もう出ない
        await pg.goto(f"{BASE}?now=2026-11-20T08:27")
        await pg.fill("#email", "me@example.com"); await pg.click("[data-act=send]")
        await pg.wait_for_selector("#name"); await pg.fill("#name", "岡山 太郎"); await pg.click("[data-act=savename]")
        await pg.wait_for_selector(".guide")
        check("氏名入力後に使い方の案内が出る（1/4）", "1 / 4" in await pg.locator(".guide h2").inner_text())
        check("最初のページにはチェック欄・確認ボタンがない", await pg.locator("#guidehide").count() == 0 and await pg.locator("[data-act=guideok]").count() == 0)
        for i in range(4):
            await pg.wait_for_timeout(350); await pg.screenshot(path=str(SHOTS / f"guide{i+1}.png"), full_page=True)
            if i < 3: await pg.click(".gnav [data-act=gpage]:has-text('次へ')")
        check("4ページ目にチェック欄と確認ボタン", await pg.locator("#guidehide").count() == 1 and await pg.locator("[data-act=guideok]").count() == 1)
        await pg.check("#guidehide"); await pg.evaluate("render(true)")
        check("自動の再描画でチェックが外れない", await pg.locator("#guidehide").is_checked())
        await pg.uncheck("#guidehide")
        await pg.click(".gnav [data-act=gpage]:has-text('戻る')")
        check("戻るで前のページへ", "3 / 4" in await pg.locator(".guide h2").inner_text())
        await guide_finish(pg, False); await pg.wait_for_selector(".vsel")
        await pg.reload(); await pg.wait_for_timeout(300)
        check("チェックなしなら次回も案内が出る", await pg.locator(".guide").count() == 1)
        await guide_finish(pg, True); await pg.wait_for_selector(".vsel")
        await pg.reload(); await pg.wait_for_timeout(300)
        check("「今後表示しない」なら次回は出ない", await pg.locator(".guide").count() == 0 and await pg.locator(".vsel").count() == 1)
        await pg.click("[data-act=tab][data-v=staff]"); await pg.click("[data-act=guide]")
        check("スタッフタブから使い方を見直せる", await pg.locator(".guide").count() == 1)
        await guide_finish(pg, False)
        await pg.click("header .help")
        check("見出しの「？」から使い方を見直せる", await pg.locator(".guide").count() == 1 and "1 / 4" in await pg.locator(".guide h2").inner_text())
        for i in range(3): await pg.click(".gnav [data-act=gpage]:has-text('次へ')")
        check("「？」から開いたときは「今後表示しない」を出さない", await pg.locator("#guidehide").count() == 0 and await pg.locator("[data-act=guideok]").count() == 1)
        await pg.click("[data-act=guideok]")
        await pg.reload(); await pg.wait_for_timeout(300)
        check("「？」から見て確認しても「今後表示しない」の記憶は変わらない", await pg.locator(".guide").count() == 0)
        await pg.click("header .help"); await pg.click(".gnav [data-act=gpage]:has-text('次へ')")
        check("各ページに × がある", await pg.locator(".gclose").count() == 1)
        await pg.click(".gclose")
        check("× で閉じられる", await pg.locator(".guide").count() == 0 and await pg.locator(".vsel").count() == 1)

        await login(pg, "2026-11-20T08:27")
        check("初期状態では会場カードを出さない", await pg.locator(".card").count() == 0)
        await pg.evaluate("""(async()=>{await api.addAssignment('d1v1-0830','me@example.com');
            api.demoCheckIn('d1v1-0820',1,'demo-1');api.demoCheckIn('d1v2-0830',2,'demo-2');
            api.demoComment('d1v1-0820','demo-1','調光卓前にいます');await refresh()})()""")
        await pg.wait_for_timeout(200)
        check("次の担当の通知が出る", "8:30～ 第1会場のスタッフ担当です。" in " ".join(await pg.locator(".mine").all_inner_texts()))
        check("会場ボタン・タブにはバッジを出さない", await pg.locator(".badge").count() == 0)
        await pg.click(".vbtn.v1")
        check("未読コメント数のバッジ（コメント欄の帯）", await pg.locator(".cbar .badge").all_inner_texts() == ["1"])
        await pg.click(".card [data-act=in]"); await pg.wait_for_selector(".inmark")
        check("入室できる", await pg.locator(".card .count .n").inner_text() == "2")
        check("コメントは開くまで見えない", await pg.locator(".cm-b").count() == 0)
        await pg.click(".venue-h"); await pg.wait_for_timeout(500)
        check("入室前のコメントも見える", await pg.locator(".cm-b").all_inner_texts() == ["調光卓前にいます"])
        await pg.fill("#cm-1", "了解<b>"); await pg.press("#cm-1", "Enter"); await pg.wait_for_timeout(300)
        check("コメント送信（HTMLはエスケープ）", (await pg.locator(".cm-b").all_inner_texts())[-1] == "了解<b>")
        check("コメント欄を開くと既読になりバッジが消える（自分のコメントは数えない）", await pg.locator(".badge").count() == 0)
        # ゆっくり入力している間に自動更新が来ても、入力中の文字が消えず、送信ボタンを（人の速さで）押せば送れる
        await pg.click("#cm-1"); await pg.keyboard.type("ゆっくり入力")
        await pg.evaluate("refresh()"); await pg.wait_for_timeout(300)
        bx = await pg.locator("[data-act=csend]").first.bounding_box()
        await pg.mouse.move(bx["x"]+10, bx["y"]+10); await pg.mouse.down(); await pg.wait_for_timeout(200); await pg.mouse.up(); await pg.wait_for_timeout(700)
        check("入力中に自動更新が来ても、送信ボタンでコメントを送れる", (await pg.locator(".cm-b").all_inner_texts())[-1] == "ゆっくり入力")
        await pg.click("#cm-1"); await pg.keyboard.type("途中"); await pg.evaluate("refresh()")
        await pg.locator(".card .title").first.click(); await pg.wait_for_timeout(600)
        check("入力欄から離れて自動更新されても、入力途中の文字は残る", await pg.locator("#cm-1").input_value() == "途中")
        await pg.fill("#cm-1", "")
        await pg.click(".cbar"); await pg.evaluate("api.demoComment('d1v1-0820','demo-2','照明OKです');refresh()"); await pg.wait_for_timeout(300)
        check("閉じている間に届いたコメントは再びバッジ表示", await pg.locator(".cbar .badge").all_inner_texts() == ["1"])
        await pg.evaluate("window.scrollTo(0,0)"); await pg.screenshot(path=str(SHOTS / "badge.png"))
        await pg.click(".cbar"); await pg.wait_for_timeout(300)
        await pg.evaluate("window.scrollTo(0,0)"); await pg.wait_for_timeout(2700); await pg.screenshot(path=str(SHOTS / "now.png"))
        await pg.click(".vbtn.v2"); await pg.wait_for_timeout(200)
        check("別会場に切替えると第1会場のコメントは出ない", await pg.locator(".cm-b").count() == 0)

        await login(pg, "2026-11-20T09:10")
        await pg.click(".vbtn.v1")
        check("時刻で次のプログラムに切替わる", await pg.locator(".card .title").inner_text() == "シンポジウム1")
        check("切替後は再び入室を押せる", await pg.locator(".card [data-act=in]").count() == 1)
        await pg.click(".venue-h"); await pg.wait_for_timeout(300)
        check("終了したプログラムのコメントは消える", await pg.locator(".cm-b").count() == 0)
        await pg.click(".card [data-act=in]"); await pg.wait_for_selector(".inmark")
        await pg.click(".vbtn.v2"); await pg.click(".card [data-act=in]"); await pg.wait_for_selector(".inmark")
        await pg.click(".vbtn.v1"); await pg.wait_for_timeout(200)
        check("同時間帯の別会場に入室すると前の会場は取消", await pg.locator(".inmark").count() == 0)

        await pg.click("[data-v=sched]"); await pg.wait_for_timeout(200)
        check("日程表：開催中が太枠", await pg.locator(".blk.live .bn").all_inner_texts() == ["シンポジウム1", "シンポジウム2"])
        check("日程表：自分の担当に印", await pg.locator(".blk.myduty .bn").all_inner_texts() == ["シンポジウム1"])
        await pg.click("[data-act=zoom][data-v='1']"); await pg.wait_for_timeout(100)
        w0 = await pg.evaluate("document.querySelector('.tt-wrap').clientWidth")
        check("拡大できる（横スクロールになる）", await pg.evaluate("document.querySelector('.tt-wrap').scrollWidth") > w0 * 1.2)
        await pg.screenshot(path=str(SHOTS / "sched_zoom_in.png"))
        for _ in range(4): await pg.click("[data-act=zoom][data-v='-1']")
        r = await pg.evaluate("(()=>{const a=document.querySelector('.tt').getBoundingClientRect(),w=document.querySelector('.tt-wrap');return [a.width,w.clientWidth,a.height,w.clientHeight,getComputedStyle(w).overflowX]})()")
        check("縮小できる（幅は画面いっぱい・高さは半分）", await pg.locator(".zoom .pct").inner_text() == "50%" and abs(r[0]-r[1]) < 3 and abs(r[2]-r[3]) < 3 and r[4] == 'hidden')
        await pg.screenshot(path=str(SHOTS / "sched_zoom_out.png"))
        await pg.click(".zoom .pct"); await pg.wait_for_timeout(100)
        check("100%に戻せる", await pg.locator(".zoom .pct").inner_text() == "100%")
        # 2本指ピンチ：指を置いた位置の内容が、拡大後も指の下に残る
        cdp = await pg.context.new_cdp_session(pg)
        await cdp.send("Emulation.setTouchEmulationEnabled", {"enabled": True})
        fx, fy = 300, 600
        before = await pg.evaluate(f"zoomAnchor({fx},{fy})")
        async def touch(kind, d):
            pts = [] if kind == "touchEnd" else [{"x": fx-d, "y": fy, "id": 1}, {"x": fx+d, "y": fy, "id": 2}]
            await cdp.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": pts})
        await touch("touchStart", 30)
        for d in (40, 50, 60): await touch("touchMove", d)
        await touch("touchEnd", 0); await pg.wait_for_timeout(100)
        after = await pg.evaluate(f"zoomAnchor({fx},{fy})")
        check("ピンチで拡大できる（200%）", await pg.locator(".zoom .pct").inner_text() == "200%")
        check("ピンチは指を置いた位置を中心に拡大", abs(before["cx"]-after["cx"]) < 2 and abs(before["cy"]-after["cy"]) < 2)
        await pg.screenshot(path=str(SHOTS / "sched_pinch.png"))
        sl = await pg.evaluate("document.querySelector('.tt-wrap').scrollLeft")
        await pg.evaluate("render()")
        check("自動更新で拡大中の横位置が戻らない", sl > 0 and await pg.evaluate("document.querySelector('.tt-wrap').scrollLeft") == sl)
        before = await pg.evaluate("viewCenterAnchor()")
        await pg.evaluate("document.querySelector(\"[data-act=zoom][data-v='-1']\").click()"); await pg.wait_for_timeout(100)   # 画面をスクロールさせずに押す
        after = await pg.evaluate(f"zoomAnchor({before['sx']},{before['sy']})")
        if not (abs(before["cx"]-after["cx"]) < 2 and abs(before["cy"]-after["cy"]) < 2): print(before, after)
        check("－ボタンは見えている部分の中央を中心に縮小", abs(before["cx"]-after["cx"]) < 2 and abs(before["cy"]-after["cy"]) < 2)
        await pg.click(".zoom .pct"); await pg.wait_for_timeout(100)
        await pg.screenshot(path=str(SHOTS / "sched.png"), full_page=True)
        await pg.click(".blk.live >> nth=0"); await pg.wait_for_selector(".sheet")
        await pg.select_option(".sheet select", "staff3@example.com"); await pg.click("[data-act=assign]"); await pg.wait_for_timeout(300)
        check("管理者は担当を追加できる", "高橋 美咲" in " ".join(await pg.locator(".sheet .duty-p").all_inner_texts()))
        await pg.mouse.click(195, 60); await pg.wait_for_timeout(200)
        check("詳細シートを閉じられる", await pg.locator(".sheet").count() == 0)
        check("管理者には表示切替がある", await pg.locator("[data-act=schedall]").count() == 2)
        # スタッフ（管理者でない人）の見え方：切替ボタンなし・担当を割り振ったプログラムのみ
        await pg.evaluate("""(async()=>{for(const e of dutyOf('d1v2-0830')) await api.removeAssignment('d1v2-0830',e);
            await api.setAdmin('me@example.com',false);await refresh()})()""")
        await pg.wait_for_timeout(200)
        check("スタッフには表示切替を出さない", await pg.locator("[data-act=schedall]").count() == 0)
        check("スタッフには担当のないプログラムを出さない", "シンポジウム2" not in await pg.locator(".tt").inner_text())
        await pg.evaluate("(async()=>{await api.setAdmin('me@example.com',true);await refresh()})()")
        await pg.wait_for_timeout(200)

        await pg.click("[data-v=staff]"); await pg.wait_for_timeout(200)
        check("スタッフ一覧に「会場外」を出さない", "会場外" not in await pg.locator("main").inner_text())
        await pg.screenshot(path=str(SHOTS / "staff.png"), full_page=True)

        await login(pg, "2026-11-21T19:30"); await pg.click(".vbtn.v1")
        check("翌日分は当日まで入室不可", await pg.locator(".card .btn").is_disabled())
        await login(pg, "2026-11-22T17:30"); await pg.click(".vbtn.v1")
        check("全日程終了の表示", "全日程が終了しました" in await pg.locator(".card").inner_text())

        # テストモード（学会前の夜 11/15 19:00 に、管理者が「1日目 9:10」から開始）
        ctx = await b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        t2 = await ctx.new_page()
        t2.on("pageerror", lambda e: errs.append(str(e)))
        t2.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
        await t2.clock.set_fixed_time("2026-11-15T19:00:00+09:00")
        await login(t2, "")
        await t2.goto(BASE); await t2.wait_for_selector(".vsel")
        await t2.click(".vbtn.v1")
        check("テスト前は入室ボタンを押せない", await t2.locator(".card .btn").is_disabled())
        await t2.click("[data-v=staff]"); await t2.select_option("#tday", "1"); await t2.fill("#ttime", "09:10")
        await t2.click("[data-act=teststart]"); await t2.wait_for_selector(".banner.test")
        check("テスト中の帯が全タブに出る", "11/20(金) 9:10 として動いています" in await t2.locator(".banner.test").inner_text())
        await t2.click("[data-v=now]"); await t2.click(".vbtn.v1")
        check("テスト中は指定時刻のプログラムを表示", await t2.locator(".card .title").inner_text() == "シンポジウム1")
        await t2.click(".card [data-act=in]"); await t2.wait_for_selector(".inmark")
        check("テスト中は入室できる（時刻もテストの時刻）", "09:10" in await t2.locator(".pill.me-p").inner_text())
        await t2.click(".cbar"); await t2.fill("#cm-1", "テスト送信"); await t2.press("#cm-1", "Enter"); await t2.wait_for_timeout(300)
        check("テスト中はコメントを送受信できる", "テスト送信" in " ".join(await t2.locator(".cm-b").all_inner_texts()))
        await t2.click("[data-v=sched]"); await t2.wait_for_timeout(200)
        check("テスト中は日程表もテスト時刻（開催中が太枠）", "シンポジウム1" in await t2.locator(".blk.live .bn").all_inner_texts())
        await t2.screenshot(path=str(SHOTS / "test_sched.png"))
        await t2.click("[data-v=staff]"); await t2.wait_for_timeout(200)
        await t2.screenshot(path=str(SHOTS / "test_panel.png"), full_page=True)
        await t2.click("[data-act=testclear]"); await t2.wait_for_timeout(400)
        n = await t2.evaluate("JSON.parse(localStorage.getItem('staff-board-demo-v1')).checkins.length + JSON.parse(localStorage.getItem('staff-board-demo-v1')).comments.length")
        check("テストの記録を消去すると入室・コメントが消えテスト停止", n == 0 and await t2.locator(".banner.test").count() == 0)
        await t2.click("[data-act=teststart]"); await t2.wait_for_selector(".banner.test")   # 設定を残したまま当日を迎えた場合
        await t2.close()
        t3 = await ctx.new_page()   # 同じブラウザ環境（同じ端末）で当日に開き直す
        t3.on("pageerror", lambda e: errs.append(str(e)))
        await t3.clock.set_fixed_time("2026-11-20T07:00:00+09:00")
        await t3.goto(BASE); await t3.wait_for_selector(".vsel"); await t3.click("[data-v=staff]"); await t3.wait_for_timeout(200)
        check("学会当日はテストモードが自動で無効（帯・操作欄なし）", await t3.locator(".banner.test").count() == 0 and await t3.locator("[data-act=teststart]").count() == 0)
        check("JavaScriptエラーなし", not errs)
        if errs: print(errs)
        await b.close()
    print("\n" + ("すべて OK" if not fails else f"NG {len(fails)}件: {fails}"))
    sys.exit(1 if fails else 0)

asyncio.run(main())
