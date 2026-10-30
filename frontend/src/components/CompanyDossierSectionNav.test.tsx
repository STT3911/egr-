/** @vitest-environment jsdom */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CompanyDossierSectionNav } from "./CompanyDossierSectionNav";

describe("CompanyDossierSectionNav", () => {
  it("offers only the two requested top-level sections", () => {
    render(<CompanyDossierSectionNav profile={{
      unp: 1, current_status_name: "Действующий", names: [], addresses: [{ full_address: "x" }], ved: [], contacts: [],
      trade_registry_records: [{ registration_number: "1" }], contacts_aggregated: [],
    }} />);
    expect(screen.getByRole("link", { name: /ЕГР/ }).getAttribute("href")).toBe("#egr-section");
    expect(screen.getByRole("link", { name: /Торговый реестр/ }).getAttribute("href")).toBe("#trade-registry-section");
    expect(screen.queryByText(/Суд/)).toBeNull();
  });
});
