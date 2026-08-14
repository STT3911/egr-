import { differenceInYears, isValid, parseISO } from "date-fns";

export const getCompanyAgeYears = (
  registrationDate?: string | null,
  liquidationDate?: string | null,
  today: Date = new Date(),
): number | null => {
  if (!registrationDate) return null;

  const registeredAt = parseISO(registrationDate);
  const endedAt = liquidationDate ? parseISO(liquidationDate) : today;
  if (!isValid(registeredAt) || !isValid(endedAt) || endedAt < registeredAt) return null;

  return differenceInYears(endedAt, registeredAt);
};
