/** @vitest-environment jsdom */

import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { lookupCompanies } from "@/lib/api";
import { CompanySearch } from "./CompanySearch";

vi.mock("@/lib/api", () => ({
  lookupCompanies: vi.fn(),
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((promiseResolve) => {
    resolve = promiseResolve;
  });
  return { promise, resolve };
}

describe("CompanySearch", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("does not replace fresh suggestions with a stale response", async () => {
    vi.useFakeTimers();
    const oldResponse = deferred<{
      query: string;
      count: number;
      results: Array<{ unp: number; name: string; full_name_ru: string }>;
    }>();
    const freshResponse = deferred<{
      query: string;
      count: number;
      results: Array<{ unp: number; name: string; full_name_ru: string }>;
    }>();
    vi.mocked(lookupCompanies)
      .mockReturnValueOnce(oldResponse.promise)
      .mockReturnValueOnce(freshResponse.promise);

    render(
      <MemoryRouter>
        <CompanySearch />
      </MemoryRouter>,
    );

    const input = screen.getByPlaceholderText("УНП, название, телефон, email или адрес");
    fireEvent.change(input, { target: { value: "старый" } });
    await act(() => vi.advanceTimersByTimeAsync(300));
    const oldSignal = vi.mocked(lookupCompanies).mock.calls[0][1];
    expect(oldSignal?.aborted).toBe(false);

    fireEvent.change(input, { target: { value: "новый" } });
    expect(oldSignal?.aborted).toBe(true);
    await act(() => vi.advanceTimersByTimeAsync(300));

    await act(async () => {
      freshResponse.resolve({
        query: "новый",
        count: 1,
        results: [{ unp: 222222222, name: "Новое", full_name_ru: "Новое" }],
      });
      await freshResponse.promise;
    });
    expect(screen.getByText("Новое")).toBeTruthy();

    await act(async () => {
      oldResponse.resolve({
        query: "старый",
        count: 1,
        results: [{ unp: 111111111, name: "Старое", full_name_ru: "Старое" }],
      });
      await oldResponse.promise;
    });

    expect(screen.queryByText("Старое")).toBeNull();
    expect(screen.getByText("Новое")).toBeTruthy();
  });
});
