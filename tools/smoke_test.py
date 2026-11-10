"""デモモードでの動作確認（Supabase不要）。
準備:  pip install playwright && playwright install chromium
実行:  python3 tools/smoke_test.py      （リポジトリ直下で）
結果:  すべて OK と表示されれば成功。tools/shots/ に画面キャプチャを保存します。
"""
import asyncio, pathlib, sys
from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE = (ROOT / "index.html").as_uri()
SHOTS = ROOT / "tools" / "shots"
fails = []
def check(name, cond):
    print(("OK  " if cond else "NG  ") + name)
    if not cond: fails.append(name)

async def login(pg, now):
    await pg.goto(f"{BASE}?now={now}")
    if await pg.locator("#email").count():
        await pg.fill("#email", "me@example.com"); await pg.click("[data-act=send]")
        await pg.wait_for_selector("#name"); await pg.fill("#name", "岡山 太郎"); await pg.click("[data-act=savename]")
    await pg.wait_for_selector(".vsel")

async def main():
    SHOTS.mkdir(exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))

        await login(pg, "2026-11-20T08:27")
        check("初期状態では会場カードを出さない", await pg.locator(".card").count() == 0)
        await pg.evaluate("""(async()=>{await api.addAssignment('d1v1-0830','me@example.com');
            api.demoCheckIn('d1v1-0820',1,'demo-1');api.demoCheckIn('d1v2-0830',2,'demo-2');
            api.demoComment('d1v1-0820','demo-1','調光卓前にいます');await refresh()})()""")
        await pg.wait_for_timeout(200)
        check("次の担当の通知が出る", "8:30～ 第1会場のスタッフ担当です。" in " ".join(await pg.locator(".mine").all_inner_texts()))
        await pg.click(".vbtn.v1"); await pg.click(".card [data-act=in]"); await pg.wait_for_selector(".inmark")
        check("入室できる", await pg.locator(".card .count .n").inner_text() == "2")
        check("コメントは開くまで見えない", await pg.locator(".cm-b").count() == 0)
        await pg.click(".venue-h"); await pg.wait_for_timeout(500)
        check("入室前のコメントも見える", await pg.locator(".cm-b").all_inner_texts() == ["調光卓前にいます"])
        await pg.fill("#cm-1", "了解<b>"); await pg.press("#cm-1", "Enter"); await pg.wait_for_timeout(300)
        check("コメント送信（HTMLはエスケープ）", (await pg.locator(".cm-b").all_inner_texts())[-1] == "了解<b>")
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
        check("JavaScriptエラーなし", not errs)
        if errs: print(errs)
        await b.close()
    print("\n" + ("すべて OK" if not fails else f"NG {len(fails)}件: {fails}"))
    sys.exit(1 if fails else 0)

asyncio.run(main())
