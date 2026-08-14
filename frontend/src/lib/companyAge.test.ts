import { describe, expect, it } from "vitest";

import { getCompanyAgeYears } from "./companyAge";

describe("getCompanyAgeYears", () => {
  it("stops counting at the liquidation date", () => {
    expect(getCompanyAgeYears("2014-07-21", "2018-08-15", new Date("2026-08-14"))).toBe(4);
  });

  it("uses today for an active company", () => {
    expect(getCompanyAgeYears("2014-07-21", null, new Date("2026-08-14"))).toBe(12);
  });

  it("counts only completed years", () => {
    expect(getCompanyAgeYears("2014-09-01", "2018-08-15")).toBe(3);
  });

  it("rejects invalid date ranges", () => {
    expect(getCompanyAgeYears("2020-01-01", "2019-01-01")).toBeNull();
  });
});
