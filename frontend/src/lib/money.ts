/**
 * Money is always integer minor units (cents). Parsing from user input is done
 * on the decimal string, never through floating-point arithmetic.
 */
const DECIMAL = /^(0|[1-9]\d{0,8})(\.\d{1,2})?$/;

export function parseAmountToMinor(input: string): number | null {
  const text = input.trim().replace(/,/g, "");
  if (!DECIMAL.test(text)) return null;
  const [whole = "0", fraction = ""] = text.split(".");
  const minor = Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
  return Number.isSafeInteger(minor) && minor > 0 ? minor : null;
}

export function formatMinor(minor: number, currency = "USD"): string {
  const sign = minor < 0 ? "-" : "";
  const abs = Math.abs(minor);
  const whole = Math.floor(abs / 100).toLocaleString("en-US");
  const cents = String(abs % 100).padStart(2, "0");
  return `${sign}${currency === "USD" ? "$" : ""}${whole}.${cents}`;
}
