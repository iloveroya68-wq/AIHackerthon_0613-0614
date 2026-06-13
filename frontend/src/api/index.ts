import { incidentClient } from "./incident/client";
import { incidentMock } from "./incident/mock";
import { riskClient } from "./risk/client";
import { riskMock } from "./risk/mock";

const useMock = import.meta.env.VITE_USE_MOCK === "true";

export const api = {
  ...(useMock ? incidentMock : incidentClient),
  ...(useMock ? riskMock : riskClient),
};
