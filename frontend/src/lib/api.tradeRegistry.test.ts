/** @vitest-environment jsdom */

import { afterEach, describe, expect, it, vi } from "vitest";

import { createTradeRegistryImport } from "./api";

describe("createTradeRegistryImport", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("explains a proxy upload-size rejection", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 413,
      }),
    );

    const file = new File(["csv"], "mart.csv", { type: "text/csv" });

    await expect(createTradeRegistryImport(file)).rejects.toThrow(
      "CSV слишком большой. Максимальный размер файла — 512 МБ",
    );
  });
});
