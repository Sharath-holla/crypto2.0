export async function api<T>(
  path: string,
  body?: unknown,
  method = body === undefined ? "GET" : "POST",
): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method,
    headers:
      body instanceof FormData
        ? { "X-Request-ID": crypto.randomUUID() }
        : {
            "Content-Type": "application/json",
            "X-Request-ID": crypto.randomUUID(),
          },
    body:
      body === undefined
        ? undefined
        : body instanceof FormData
          ? body
          : JSON.stringify(body),
    cache: "no-store",
  });
  const result = await response.json();
  if (!response.ok)
    throw new Error(
      typeof result.detail === "string"
        ? result.detail
        : JSON.stringify(result.detail),
    );
  return result as T;
}
export const money = (micro: number | null | undefined) =>
  micro == null
    ? "Not verified"
    : new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: micro < 10000 && micro > 0 ? 6 : 2,
      }).format(micro / 1000000);
export const date = (epoch: number) => new Date(epoch * 1000).toLocaleString();
