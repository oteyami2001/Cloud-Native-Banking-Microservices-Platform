import { challengeFor, randomString } from "../src/lib/pkce";

describe("PKCE", () => {
  it("matches the RFC 7636 appendix B example", async () => {
    expect(await challengeFor("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk")).toBe("E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM");
  });
  it("produces url-safe random verifiers", () => {
    const v = randomString(48);
    expect(v).toMatch(/^[A-Za-z0-9_-]{64}$/);
    expect(randomString(48)).not.toBe(v);
  });
});
