import type {
  ApiError,
  DropGroup,
  GameEvent,
  GameRates,
  HealthResponse,
  ListEnvelope,
  ProvisionPayload,
  SpawnArea,
  TenantDetail,
  TenantListResponse,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  const text = await response.text();
  const data = text ? (JSON.parse(text) as T | ApiError | { message?: string }) : ({} as T);
  if (!response.ok) {
    const err = data as ApiError & { message?: string };
    const detail = err.detail;
    const message =
      typeof detail === "string"
        ? detail
        : detail?.error || err.message || `Request failed (${response.status})`;
    throw new Error(message);
  }
  return data as T;
}

export const api = {
  health: () => request<HealthResponse>("/api/health"),
  tenants: () => request<TenantListResponse>("/api/tenants"),
  tenant: (ns: string) => request<TenantDetail>(`/api/tenants/${ns}`),
  restartDeployment: (ns: string, name: string) =>
    request(`/api/tenants/${ns}/deployments/${name}/restart`, {
      method: "POST",
      body: JSON.stringify({ reason: "panel" }),
    }),
  restartPod: (ns: string, name: string) =>
    request(`/api/tenants/${ns}/pods/${name}/restart`, {
      method: "POST",
      body: JSON.stringify({ reason: "panel" }),
    }),
  rates: (ns: string) => request<GameRates>(`/api/tenants/${ns}/game/rates`),
  saveRates: (ns: string, rates: GameRates) =>
    request<GameRates>(`/api/tenants/${ns}/game/rates`, {
      method: "PUT",
      body: JSON.stringify(rates),
    }),
  drops: (ns: string) => request<ListEnvelope<DropGroup>>(`/api/tenants/${ns}/game/drops`),
  saveDrop: (ns: string, id: string, chance: number) =>
    request<DropGroup>(`/api/tenants/${ns}/game/drops/${id}`, {
      method: "PUT",
      body: JSON.stringify({ chance }),
    }),
  spawns: (ns: string) => request<ListEnvelope<SpawnArea>>(`/api/tenants/${ns}/game/spawns`),
  saveSpawn: (ns: string, id: string, quantity: number) =>
    request<SpawnArea>(`/api/tenants/${ns}/game/spawns/${id}`, {
      method: "PUT",
      body: JSON.stringify({ quantity }),
    }),
  events: (ns: string) => request<ListEnvelope<GameEvent>>(`/api/tenants/${ns}/game/events`),
  saveEvent: (ns: string, id: string, body: Partial<GameEvent>) =>
    request<GameEvent>(`/api/tenants/${ns}/game/events/${id}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  provision: (payload: ProvisionPayload) =>
    request("/api/servers", { method: "POST", body: JSON.stringify(payload) }),
};
