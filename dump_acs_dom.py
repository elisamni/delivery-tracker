from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

from delivery_tracker.config import get_settings


def dump_acs_dom(tracking_number: str, output_file: str) -> Path:
    settings = get_settings()
    output_path = Path(output_file).resolve()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=settings.playwright_headless)
        try:
            context = browser.new_context(
                user_agent=settings.playwright_user_agent,
                locale=settings.playwright_locale,
            )
            page = context.new_page()
            page.set_default_timeout(settings.playwright_timeout_ms)
            page.goto(settings.acs_tracking_url, wait_until="domcontentloaded")
            page.wait_for_timeout(2_000)

            page.evaluate(
                """
                () => {
                    const cookieBtn = document.querySelector('#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll');
                    if (cookieBtn) cookieBtn.click();
                    const dialog = document.querySelector('#CybotCookiebotDialog');
                    if (dialog) dialog.remove();
                    const chat = document.querySelector('#aseto-chat-widget');
                    if (chat) chat.remove();
                }
                """
            )
            page.wait_for_timeout(500)

            field = page.locator("input[name='trackingNumbers']").first
            field.fill(tracking_number)
            search = page.get_by_role("button", name="Search").first
            if search.count():
                search.click(force=True)
            else:
                page.evaluate(
                    """
                    () => {
                        const btn = Array.from(document.querySelectorAll('button')).find(
                            el => (el.textContent || '').includes('Search')
                        );
                        if (btn) btn.click();
                    }
                    """
                )

            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(5_000)
            output_path.write_text(page.content(), encoding="utf-8")
            return output_path
        finally:
            browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Dump ACS DOM after running a search")
    parser.add_argument("--tracking-number", required=True)
    parser.add_argument("--output", default="acs_dom_dump.html")
    args = parser.parse_args()

    output = dump_acs_dom(args.tracking_number, args.output)
    print(output)


if __name__ == "__main__":
    main()
