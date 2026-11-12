import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";

const base = process.env.API_INTERNAL_URL || "http://127.0.0.1:8000";
async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  if (path.some((segment) => !/^[a-zA-Z0-9_-]+$/.test(segment)))
    return NextResponse.json({ detail: "Invalid path" }, { status: 400 });
  if (request.method !== "GET") {
    const origin = request.headers.get("origin");
    const expected = process.env.WEB_ORIGIN || "http://localhost:3000";
    const allowed =
      origin === expected ||
      (process.env.NODE_ENV !== "production" &&
        origin === "http://127.0.0.1:3000");
    if (!allowed)
      return NextResponse.json({ detail: "Origin rejected" }, { status: 403 });
  }
  const jar = await cookies();
  const endpoint = path.join("/");
  const token = jar.get("company-session")?.value;
  const headers: Record<string, string> = {};
  const contentType = request.headers.get("content-type");
  if (contentType) headers["Content-Type"] = contentType;
  if (token) headers.Authorization = `Bearer ${token}`;
  const suppliedId = request.headers.get("x-request-id") || "";
  headers["X-Request-ID"] = /^[A-Za-z0-9_-]{8,64}$/.test(suppliedId)
    ? suppliedId
    : crypto.randomUUID();
  try {
    const streaming =
      request.method === "GET" &&
      path[0] === "conversations" &&
      path[2] === "events";
    const checkoutCommand =
      request.method === "POST" &&
      ((path.length === 3 &&
        path[0] === "repositories" &&
        path[2] === "checkout") ||
        (path.length === 3 &&
          path[0] === "repository-checkouts" &&
          ["execute", "reconcile", "cleanup"].includes(path[2])));
    const response = await fetch(
      `${base}/${endpoint}${request.nextUrl.search}`,
      {
        method: request.method,
        headers,
        body:
          request.method === "GET" ? undefined : await request.arrayBuffer(),
        cache: "no-store",
        signal: streaming
          ? request.signal
          : AbortSignal.timeout(checkoutCommand ? 210000 : 30000),
      },
    );
    const responseHeaders = {
      "X-Request-ID":
        response.headers.get("x-request-id") || headers["X-Request-ID"],
    };
    if (
      streaming &&
      response.ok &&
      response.headers.get("content-type")?.startsWith("text/event-stream")
    ) {
      return new Response(response.body, {
        headers: {
          ...responseHeaders,
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache",
          "X-Accel-Buffering": "no",
        },
      });
    }
    if (
      request.method === "GET" &&
      ((path[0] === "delivery-packages" && path[2] === "files") ||
        (path[0] === "delivery-cases" && path[2] === "attachments") ||
        (path[0] === "client" &&
          path[1] === "cases" &&
          path[3] === "attachments") ||
        (path[0] === "client" &&
          path[1] === "deliveries" &&
          path[3] === "files")) &&
      response.ok
    ) {
      return new Response(response.body, {
        headers: {
          ...responseHeaders,
          "Content-Type": "text/plain; charset=utf-8",
          "Content-Disposition":
            response.headers.get("content-disposition") || "attachment",
          "Cache-Control": "no-store",
          "X-Content-Type-Options": "nosniff",
        },
      });
    }
    const body = await response.json();
    if (
      endpoint === "auth/logout" &&
      (response.ok || response.status === 401)
    ) {
      jar.delete("company-session");
      return NextResponse.json({ ok: true }, { headers: responseHeaders });
    }
    if (
      ["auth/login", "auth/redeem-invitation"].includes(endpoint) &&
      response.ok
    ) {
      jar.set("company-session", body.access_token, {
        httpOnly: true,
        sameSite: "strict",
        secure: process.env.COOKIE_SECURE === "true",
        path: "/",
        maxAge: 3600,
      });
      return NextResponse.json(
        { user: body.user },
        { headers: responseHeaders },
      );
    }
    return NextResponse.json(body, {
      status: response.status,
      headers: responseHeaders,
    });
  } catch {
    return NextResponse.json(
      { detail: "Backend unavailable. Start the API and check its health." },
      { status: 503 },
    );
  }
}
export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
