import { test, expect } from '@playwright/test'

test('loads shell and shows blueprint brand', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('BLUEPRINT')).toBeVisible()
  await expect(page.getByText('Navigation')).toBeVisible()
})
