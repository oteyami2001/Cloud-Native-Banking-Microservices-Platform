import { ApiError, BankApi } from "../src/lib/api";

function fakeFetch(status: number, body: unknown) {
  return vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify(body), { status }));
}

describe("BankApi", () => {
  it("sends the bearer token and idempotency key for transfers", async () => {
    const fetchImpl = fakeFetch(201, { transfer_id: "TRF-1", status: "COMPLETED" });
    const api = new BankApi(() => "tok", "https://api.example", fetchImpl as unknown as typeof fetch);
    await api.transfer({ source_account_id: "A", destination_account_id: "B", amount_minor: 25000, currency: "USD" }, "key-1234567890abcdef");
    const [url, init] = fetchImpl.mock.calls[0]!;
    const headers = init!.headers as Record<string, string>;
    expect(url).toBe("https://api.example/v1/transfers");
    expect(headers.authorization).toBe("Bearer tok");
    expect(headers["idempotency-key"]).toBe("key-1234567890abcdef");
    expect(JSON.parse(init!.body as string).amount_minor).toBe(25000);
    expect(init!.credentials).toBe("omit");
  });

  it("maps API errors to ApiError with code and body", async () => {
    const body = { error: { code: "INSUFFICIENT_FUNDS", message: "Insufficient available balance" }, transfer: { status: "REJECTED" } };
    const api = new BankApi(() => "tok", "https://api.example", fakeFetch(422, body) as unknown as typeof fetch);
    const err = await api.balance("ACC-1").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("INSUFFICIENT_FUNDS");
    expect(err.status).toBe(422);
    expect(err.body.transfer.status).toBe("REJECTED");
  });

  it("encodes path parameters", async () => {
    const fetchImpl = fakeFetch(200, {});
    const api = new BankApi(() => null, "https://api.example", fetchImpl as unknown as typeof fetch);
    await api.account("../admin");
    expect(fetchImpl.mock.calls[0]![0]).toBe("https://api.example/v1/accounts/..%2Fadmin");
    expect((fetchImpl.mock.calls[0]![1]!.headers as Record<string, string>).authorization).toBeUndefined();
  });
});
