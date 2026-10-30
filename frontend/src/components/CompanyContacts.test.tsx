/** @vitest-environment jsdom */
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { CompanyContacts } from "./CompanyContacts";

afterEach(cleanup);

describe("CompanyContacts", () => {
  it("renders source-labelled contacts even when EGR is empty", () => {
    render(<CompanyContacts profile={{ contacts: [], contacts_aggregated: [
      { contact_type: "email", value: "mart@example.by", sources: ["mart"] },
      { contact_type: "phone", value: "+375291234567", sources: ["gias", "pvt"] },
      { contact_type: "website", value: "example.by", sources: ["manual"] },
    ] }} />);
    expect(screen.getByText("Контактная информация")).toBeTruthy();
    const email = screen.getByRole("link", { name: "mart@example.by" });
    expect(within(email.closest("li")!).getByText("МАРТ")).toBeTruthy();
    const phone = screen.getByRole("link", { name: "+375291234567" });
    expect(within(phone.closest("li")!).getByText("ГИАС")).toBeTruthy();
    expect(within(phone.closest("li")!).getByText("ПВТ")).toBeTruthy();
    expect(screen.getByText("Вручную")).toBeTruthy();
    const website = screen.getByRole("link", { name: "example.by" });
    expect(website.getAttribute("href")).toBe("https://example.by/");
    expect(website.getAttribute("rel")).toContain("noopener");
  });

  it("shows one value with both source badges and retains different emails", () => {
    render(<CompanyContacts profile={{ contacts: [{ email: "one@example.by" }], contacts_aggregated: [
      { contact_type: "email", value: "one@example.by", sources: ["mart"] },
      { contact_type: "email", value: "two@example.by", sources: ["mart"] },
    ] }} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    const first = screen.getByRole("link", { name: "one@example.by" }).closest("li")!;
    expect(within(first).getByText("ЕГР")).toBeTruthy();
    expect(within(first).getByText("МАРТ")).toBeTruthy();
    expect(screen.getByRole("link", { name: "two@example.by" })).toBeTruthy();
  });

  it("keeps unsafe source values as plain text and labels missing provenance", () => {
    render(<CompanyContacts profile={{ contacts: [], contacts_aggregated: [
      { contact_type: "website", value: "javascript:alert(1)", sources: [] },
    ] }} />);
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText("javascript:alert(1)")).toBeTruthy();
    expect(screen.getByText("Источник не указан")).toBeTruthy();
  });

  it("omits an empty section", () => {
    const { container } = render(<CompanyContacts profile={{ contacts: [] }} />);
    expect(container.innerHTML).toBe("");
  });
});
