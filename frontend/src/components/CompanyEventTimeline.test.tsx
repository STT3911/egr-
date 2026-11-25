/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CompanyEventTimeline } from "./CompanyEventTimeline";
import CompanyEvents from "@/pages/CompanyEvents";
import { getCompanyEvents } from "@/lib/api";

vi.mock("@/components/layout/Header", () => ({ Header: () => null }));
vi.mock("@/lib/api", () => ({ getCompanyEvents: vi.fn() }));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("Лента событий", () => {
  it("shows the event date with its original precision, source and contract link", () => {
    render(<MemoryRouter><CompanyEventTimeline preview unp="193879557" items={[
      { id: "month", source: "inspection", date: "2026-10", title: "Плановая проверка", details: ["Контролирующий орган"], contract_id: null },
      { id: "known", source: "gias", date: "2026-08-10", title: "Договор ГИАС", details: ["Масло моторное"], contract_id: "test-id" },
      { id: "unknown", source: "egr", date: null, title: "Регистрация", details: [], contract_id: null },
    ]} /></MemoryRouter>);
    expect(screen.getByText("10.2026").getAttribute("datetime")).toBe("2026-10");
    expect(screen.getByText("10.08.2026")).toBeTruthy();
    expect(screen.getByText("Дата не указана")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Открыть договор" }).getAttribute("href")).toBe("/contracts/test-id?fromUnp=193879557");
    expect(screen.getByRole("link", { name: "Все события" }).getAttribute("href")).toBe("/company/193879557/events");
  });

  it("loads a second server page and starts over when the filters change", async () => {
    vi.mocked(getCompanyEvents).mockImplementation(async (_unp, filters) => ({
      company_name: "ООО ПринтВайб",
      items: [{
        id: filters.cursor ?? filters.source ?? "first", source: filters.source === "gias" ? "gias" : "egr",
        date: "2026-08-25", title: filters.cursor ? "Старое событие" : filters.source ? "Договор из фильтра" : "Новое событие",
        details: [], contract_id: null,
      }],
      next_cursor: !filters.source && !filters.cursor ? "2026-08-25|first" : null,
    }));
    const queryClient = new QueryClient();
    render(<QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/company/193879557/events"]}>
        <Routes><Route path="/company/:unp/events" element={<CompanyEvents />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>);
    await screen.findByText("Новое событие");
    fireEvent.click(screen.getByRole("button", { name: "Показать ещё" }));
    await screen.findByText("Старое событие");
    expect(screen.getByText("Новое событие")).toBeTruthy();
    expect(vi.mocked(getCompanyEvents).mock.calls[1][1].cursor).toBe("2026-08-25|first");

    const filters = within(screen.getByRole("form", { name: "Фильтры событий" }));
    fireEvent.change(filters.getByLabelText("Источник"), { target: { value: "gias" } });
    fireEvent.change(filters.getByLabelText("Дата с"), { target: { value: "2026-08-01" } });
    fireEvent.click(filters.getByRole("button", { name: "Применить" }));
    await screen.findByText("Договор из фильтра");
    expect(screen.queryByText("Старое событие")).toBeNull();
    expect(vi.mocked(getCompanyEvents).mock.calls[2][1]).toMatchObject({
      limit: 20, source: "gias", date_from: "2026-08-01", cursor: undefined,
    });
  });
});
