import {
  expect,
  test as base,
  type ConsoleMessage,
  type Page
} from "@playwright/test";

type ConsoleErrorMatcher = (message: ConsoleMessage) => boolean;

const allowedConsoleErrors = new WeakMap<Page, ConsoleErrorMatcher[]>();

export function allowExpectedConsoleError(page: Page, matcher: ConsoleErrorMatcher) {
  const matchers = allowedConsoleErrors.get(page) ?? [];
  matchers.push(matcher);
  allowedConsoleErrors.set(page, matchers);
}

function consoleError(message: ConsoleMessage): string {
  const location = message.location();
  const source = location.url
    ? ` (${location.url}${location.lineNumber ? `:${location.lineNumber}` : ""})`
    : "";
  return `${message.text()}${source}`;
}

function isExpectedSignedOutProbe(message: ConsoleMessage): boolean {
  return (
    message.text() === "Failed to load resource: the server responded with a status of 401 (Unauthorized)" &&
    message.location().url.endsWith("/api/v1/auth/me")
  );
}

export const test = base.extend({
  page: async ({ page }, use) => {
    const pageErrors: string[] = [];
    const consoleErrors: string[] = [];

    page.on("pageerror", (error) => pageErrors.push(error.stack ?? error.message));
    page.on("console", (message) => {
      if (message.type() !== "error" || isExpectedSignedOutProbe(message)) return;
      const expected = allowedConsoleErrors.get(page)?.some((matcher) => matcher(message)) ?? false;
      if (!expected) consoleErrors.push(consoleError(message));
    });

    await use(page);

    expect(pageErrors, "Unexpected uncaught browser errors").toEqual([]);
    expect(consoleErrors, "Unexpected browser console errors").toEqual([]);
  }
});

export { expect };
