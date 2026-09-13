import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

type Context = { params: Promise<{ path: string[] }> };

const BACKEND = (process.env.ASSAY_BACKEND_URL || "http://127.0.0.1:8001").replace(/\/$/, "");

async function proxy(request: NextRequest, context: Context) {
  const { path } = await context.params;
  const target = new URL(`${BACKEND}/${path.map(encodeURIComponent).join("/")}`);
  target.search = request.nextUrl.search;

  const headers = new Headers();
  for (const name of ["accept", "content-type", "if-match", "x-assay-api-version"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const token = process.env.ASSAY_API_TOKEN;
  if (token) headers.set("authorization", `Bearer ${token}`);

  const body = ["GET", "HEAD"].includes(request.method)
    ? undefined
    : await request.arrayBuffer();
  const response = await fetch(target, {
    method: request.method,
    headers,
    body,
    redirect: "manual",
    cache: "no-store",
  });

  const responseHeaders = new Headers();
  for (const name of ["content-type", "content-disposition", "etag", "x-request-id"]) {
    const value = response.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: responseHeaders,
  });
}

export const GET = proxy;
export const HEAD = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
