import asyncio
from playwright.async_api import async_playwright
async def main():
 async with async_playwright() as p:
  b=await p.chromium.launch(channel='msedge',headless=True)
  page=await b.new_page(viewport={'width':1650,'height':1100});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  await page.goto('http://127.0.0.1:8096/')
  if not await page.locator('#fg-refresh').is_visible():await page.get_by_role('button',name='Luồng Thực Thi',exact=True).click(timeout=7000)
  await page.wait_for_function("document.querySelector('#fg-source .fm-badge')?.textContent.match(/^[0-9]+$/)",timeout=12000)
  print('live',await page.locator('#fg-source .fm-badge').inner_text())
  await page.get_by_role('button',name='Mô phỏng các nhánh').click()
  await page.wait_for_selector('path.fm-moving',timeout=4000)
  await page.locator('#execgraph').screenshot(path='flow-demo-today.png')
  await page.get_by_role('button',name='Tạm dừng').click()
  await page.get_by_role('button',name='Phát lại hôm nay').click()
  await page.get_by_role('button',name='Về trực tiếp').click()
  print('returned to live; errors:',errors)
  await b.close()
asyncio.run(main())
