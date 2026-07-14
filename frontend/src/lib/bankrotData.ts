const collectionKeys = [
  "items",
  "messages",
  "properties",
  "propertyReports",
  "propertyValuations",
  "sales",
  "meetings",
  "committees",
  "requirementsResults",
  "propertiesWriteOff",
  "transferredUnsoldProperty",
] as const;

const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const isEmpty = (value: unknown): boolean => {
  if (value == null || value === "") return true;
  if (Array.isArray(value)) return value.length === 0;
  if (isObject(value)) return Object.values(value).every(isEmpty);
  return false;
};

export const getBankrotPayloadCount = (payload: unknown): number => {
  if (Array.isArray(payload)) return payload.length;
  if (!isObject(payload)) return isEmpty(payload) ? 0 : 1;
  for (const key of collectionKeys) {
    if (Array.isArray(payload[key])) return payload[key].length;
  }
  return isEmpty(payload) ? 0 : 1;
};
