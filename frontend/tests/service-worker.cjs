const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "../public/sw.js"), "utf8");
const ORIGIN = "https://apex.example";

function makeWorker(networkFetch = async () => new Response("network")) {
  const listeners = new Map();
  const storage = new Map();
  const deletedCaches = [];

  const resolveKey = (key) => {
    const url = typeof key === "string" ? new URL(key, ORIGIN) : new URL(key.url);
    return url.href;
  };
  const makeCache = (name) => {
    if (!storage.has(name)) storage.set(name, new Map());
    const entries = storage.get(name);
    return {
      async addAll(files) {
        for (const file of files) {
          const url = new URL(file, ORIGIN).href;
          entries.set(url, new Response(`cached:${new URL(url).pathname}`));
        }
      },
      async match(key) {
        return entries.get(resolveKey(key));
      },
      async put(key, response) {
        entries.set(resolveKey(key), response.clone());
      },
      async delete(key) {
        return entries.delete(resolveKey(key));
      },
      async keys() {
        return [...entries.keys()].map((url) => ({ url }));
      },
    };
  };

  const caches = {
    async open(name) {
      return makeCache(name);
    },
    async keys() {
      return [...storage.keys()];
    },
    async delete(name) {
      deletedCaches.push(name);
      return storage.delete(name);
    },
  };
  const self = {
    location: { origin: ORIGIN },
    clients: { claim: async () => {} },
    addEventListener(type, listener) {
      listeners.set(type, listener);
    },
  };

  vm.runInNewContext(source, { self, caches, fetch: networkFetch, URL, Response, Promise });
  return { listeners, caches, storage, deletedCaches };
}

function eventFor(request) {
  return {
    request,
    responsePromise: null,
    lifetime: [],
    respondWith(promise) {
      this.responsePromise = Promise.resolve(promise);
    },
    waitUntil(promise) {
      this.lifetime.push(Promise.resolve(promise));
    },
  };
}

function request(pathname, { method = "GET", mode = "cors" } = {}) {
  return { url: new URL(pathname, ORIGIN).href, method, mode };
}

function basicResponse(body, url = "") {
  return {
    ok: true,
    type: "basic",
    url,
    clone() { return basicResponse(body, url); },
  };
}

async function install(worker) {
  const event = eventFor(undefined);
  worker.listeners.get("install")(event);
  await Promise.all(event.lifetime);
}

test("install pre-caches the offline page and activate removes only old app caches", async () => {
  const worker = makeWorker();
  worker.storage.set("apex-static-old", new Map());
  worker.storage.set("other-app-cache", new Map());

  await install(worker);
  const shell = worker.storage.get("apex-static-v1");
  assert.ok([...shell.keys()].some((url) => new URL(url).pathname === "/offline.html"));

  const event = eventFor(undefined);
  worker.listeners.get("activate")(event);
  await Promise.all(event.lifetime);
  assert.deepEqual(worker.deletedCaches, ["apex-static-old"]);
});

test("API, auth, nutrition and write requests bypass the service worker", () => {
  const worker = makeWorker();
  for (const pathname of [
    "/lab/documents",
    "/auth/session",
    "/nutrition/entries",
    "/activities",
  ]) {
    const event = eventFor(request(pathname));
    worker.listeners.get("fetch")(event);
    assert.equal(event.responsePromise, null, `${pathname} should not be intercepted`);
    assert.equal(event.lifetime.length, 0, `${pathname} should not be cached`);
  }

  const write = eventFor(request("/nutrition/entries", { method: "POST" }));
  worker.listeners.get("fetch")(write);
  assert.equal(write.responsePromise, null);
  assert.equal(write.lifetime.length, 0);
});

test("offline navigations use only the cached generic offline page", async () => {
  const worker = makeWorker(async () => {
    throw new TypeError("offline");
  });
  await install(worker);
  const navigation = eventFor(request("/app/sleep", { mode: "navigate" }));
  worker.listeners.get("fetch")(navigation);
  assert.match(await (await navigation.responsePromise).text(), /cached:\/offline\.html/);

  const apiRequest = eventFor(request("/lab/documents"));
  worker.listeners.get("fetch")(apiRequest);
  assert.equal(apiRequest.responsePromise, null);
});

test("only successful public assets are cached and background writes extend worker lifetime", async () => {
  let fetchCount = 0;
  const responses = [
    (request) => basicResponse("bundle", request.url),
    () => ({ ok: false, type: "basic", clone() { return this; } }),
    (request) => ({ ok: true, type: "cors", url: request.url, clone() { return this; } }),
  ];
  const worker = makeWorker(async (request) => {
    fetchCount += 1;
    return responses.shift()(request);
  });
  await install(worker);

  const event = eventFor(request("/assets/app.abc123.js"));
  worker.listeners.get("fetch")(event);
  await event.responsePromise;
  await Promise.all(event.lifetime);

  for (const pathname of ["/assets/not-found.js", "/assets/cross-origin.js"]) {
    const rejected = eventFor(request(pathname));
    worker.listeners.get("fetch")(rejected);
    await rejected.responsePromise;
    await Promise.all(rejected.lifetime);
  }

  assert.equal(fetchCount, 3);
  assert.equal(event.lifetime.length, 1);
  const shell = worker.storage.get("apex-static-v1");
  assert.ok([...shell.keys()].some((url) => url.endsWith("/assets/app.abc123.js")));
  assert.equal([...shell.keys()].some((url) => url.endsWith("/assets/not-found.js")), false);
  assert.equal([...shell.keys()].some((url) => url.endsWith("/assets/cross-origin.js")), false);
});

test("hashed bundle cache stays capped at 64 and shell files are retained", async () => {
  const worker = makeWorker(async (request) => basicResponse("bundle", request.url));
  await install(worker);

  for (let i = 0; i < 66; i += 1) {
    const event = eventFor(request(`/assets/app.${i}.js`));
    worker.listeners.get("fetch")(event);
    await event.responsePromise;
    await Promise.all(event.lifetime);
  }

  const keys = await worker.caches.open("apex-static-v1").then((cache) => cache.keys());
  const paths = keys.map((key) => new URL(key.url).pathname);
  const bundles = paths.filter((pathname) => pathname.startsWith("/assets/"));
  assert.equal(bundles.length, 64);
  assert.equal(paths.includes("/assets/app.0.js"), false);
  assert.equal(paths.includes("/assets/app.65.js"), true);
  assert.equal(paths.includes("/offline.html"), true);
});
