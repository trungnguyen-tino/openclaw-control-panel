import { test, expect } from "@playwright/test";

const KEY = process.env.OPENCLAW_MGMT_TEST_KEY ?? "f".repeat(64);

test.describe("login + dashboard happy path", () => {
  test("paste key → dashboard renders", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByText("OpenClaw Panel")).toBeVisible();
    // Switch to paste-key tab
    await page.getByRole("button", { name: "Paste API key" }).click();
    await page.locator("#k").fill(KEY);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL("/");
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  });

  test("sign-out clears stored key", async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("button", { name: "Paste API key" }).click();
    await page.locator("#k").fill(KEY);
    await page.getByRole("button", { name: "Sign in" }).click();
    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page).toHaveURL("/login");
  });
});
