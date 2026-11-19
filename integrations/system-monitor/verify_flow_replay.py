import asyncio,json
from pathlib import Path
from playwright.async_api import async_playwright
async def main():
 async with async_playwright() as pw:
  browser=await pw.chromium.launch(channel='msedge',headless=True)
  page=await browser.new_page(viewport={'width':1760,'height':1200});bad=[];posts=[]
  page.on('pageerror',lambda e:bad.append(str(e)));page.on('request',lambda r:posts.append(r.url) if r.method=='POST' else None)
  await page.goto('http://127.0.0.1:8096/')
  await page.get_by_role('button',name='Luồng Thực Thi',exact=True).click()
  await page.wait_for_function("document.querySelector('#fg-source .fm-badge')?.textContent.match(/^[0-9]+$/)")
  live=await page.evaluate("fetch('/api/flow-today').then(r=>r.json())")
  await page.clock.install()
  await page.get_by_role('button',name='Mô phỏng các nhánh').click()
  await page.clock.run_for(800)
  await page.locator('#execgraph').screenshot(path='flow-demo-today.png')
  await page.clock.run_for(48000)
  assert 'Đã phát xong' in await page.locator('.flow-live-tools').inner_text()
  demo=int(await page.locator('#fg-source .fm-badge').inner_text())
  await page.get_by_role('button',name='Phát lại hôm nay').click()
  assert await page.locator('path.fm-moving').evaluate_all("ps=>ps.some(p=>getComputedStyle(p).display!=='none' && p.getTotalLength()>0 && getComputedStyle(p).animationName==='flowDash')")
  assert await page.locator('#fg-replay-underline').evaluate("p=>p.getTotalLength()>100 && getComputedStyle(p).animationName==='flowDash' && getComputedStyle(p).strokeDasharray!=='none' && p.getPointAtLength(0).y>document.querySelector('.flow-node.fm-working').offsetTop+document.querySelector('.flow-node.fm-working').offsetHeight")
  first=await page.locator('.flow-live-tools').inner_text()
  await page.clock.run_for(400)
  assert await page.locator('.flow-live-tools').inner_text()==first
  await page.clock.run_for(310)
  assert await page.locator('.flow-live-tools').inner_text()!=first
  await page.get_by_role('button',name='Tạm dừng').click()
  assert await page.locator('path.fm-moving').count()==0
  await page.get_by_role('button',name='Tiếp tục').click()
  await page.clock.run_for(700*(len(live['events'])+4))
  assert 'Đã phát xong' in await page.locator('.flow-live-tools').inner_text()
  for k,v in live['counts'].items():assert int(await page.locator('#fg-'+k+' .fm-badge').inner_text())==v['n'],k
  await page.get_by_role('button',name='Về trực tiếp').click()
  assert not bad and not posts,(bad,posts)
  print(json.dumps(dict(day=live['day'],demo_cases=demo,replayed=len(live['events']),counts={k:v['n'] for k,v in live['counts'].items() if v['n']},active=live['active'],posts=len(posts)),ensure_ascii=True))
  await browser.close()
asyncio.run(main())
