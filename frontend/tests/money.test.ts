import { formatMinor, parseAmountToMinor } from "../src/lib/money";

describe("money", () => {
  it.each([
    ["250", 25000],
    ["250.00", 25000],
    ["0.01", 1],
    ["1,234.5", 123450],
    [" 9.99 ", 999],
  ])("parses %s exactly", (input, expected) => {
    expect(parseAmountToMinor(input)).toBe(expected);
  });

  it.each(["", "0", "0.00", "-1", "1.001", "1e3", "abc", "01.00", "NaN"])("rejects %s", (input) => {
    expect(parseAmountToMinor(input)).toBeNull();
  });

  it("avoids floating point errors", () => {
    expect(parseAmountToMinor("0.10")! + parseAmountToMinor("0.20")!).toBe(parseAmountToMinor("0.30"));
  });

  it("formats minor units", () => {
    expect(formatMinor(485000)).toBe("$4,850.00");
    expect(formatMinor(-150)).toBe("-$1.50");
  });
});
