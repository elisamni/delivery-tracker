from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from delivery_tracker.config import get_settings


def dump_cyprus_post_dom(tracking_number: str, output_file: str) -> tuple[Path, list[dict[str, object]]]:
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
            page.goto(settings.cyprus_post_tracking_url, wait_until="domcontentloaded")
            page.wait_for_timeout(3_000)

            inputs = page.evaluate(
                """
                () => Array.from(document.querySelectorAll('input, textarea')).map((el, index) => {
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return {
                        index,
                        tag: el.tagName,
                        type: el.getAttribute('type'),
                        name: el.getAttribute('name'),
                        placeholder: el.getAttribute('placeholder'),
                        classes: el.className,
                        visible: !!(rect.width && rect.height) &&
                            style.visibility !== 'hidden' &&
                            style.display !== 'none' &&
                            style.opacity !== '0',
                        disabled: !!el.disabled,
                        readonly: !!el.readOnly,
                        rect: {
                            x: rect.x,
                            y: rect.y,
                            width: rect.width,
                            height: rect.height,
                        },
                    };
                })
                """
            )

            page_content = page.content()
            output_path.write_text(page_content, encoding="utf-8")

            for selector in (
                "input[name='query']",
                "input[type='text']",
                "input[placeholder*='track' i]",
                "input[placeholder*='Type and hit enter' i]",
                "textarea",
            ):
                locator = page.locator(selector)
                if locator.count():
                    try:
                        locator.first.fill(tracking_number, timeout=5_000)
                        page.keyboard.press("Enter")
                        page.wait_for_timeout(3_000)
                        output_path.write_text(page.content(), encoding="utf-8")
                        break
                    except Exception:
                        continue

            return output_path, inputs
        finally:
            browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Dump Cyprus Post DOM and visible inputs")
    parser.add_argument("--tracking-number", required=True)
    parser.add_argument("--output", default="cyprus_post_dom_dump.html")
    args = parser.parse_args()

    output, inputs = dump_cyprus_post_dom(args.tracking_number, args.output)
    print(output)
    print(json.dumps(inputs, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
