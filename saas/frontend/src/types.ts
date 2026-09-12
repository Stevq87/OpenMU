export type PodLifecycle = "Running" | "Stopped" | "Crash" | "Pending" | "Starting" | "Unknown";

export type ClusterHealth = {
  connected: boolean;
  mode: string | null;
  error: string | null;
  lab_mode: boolean;
  lab_namespace: string;
  api_server: string;
  kubeconfig_path: string | null;
};

export type HealthResponse = {
  status: "ok" | "degraded";
  kubernetes: ClusterHealth;
  database: {
    configured: boolean;
    host: string | null;
    port: number | null;
    database: string | null;
    user: string | null;
    error: string | null;
  };
};

export type EndpointInfo = {
  name: string;
  namespace: string;
  service_type: string;
  ip: string | null;
  port: number | null;
  node_port: number | null;
  protocol: string;
  component: string | null;
  note: string | null;
};

export type PodInfo = {
  name: string;
  namespace: string;
  status: PodLifecycle;
  phase: string | null;
  ready: boolean;
  restarts: number;
  node: string | null;
  deployment: string | null;
  component: string | null;
  reason: string | null;
};

export type DeploymentInfo = {
  name: string;
  namespace: string;
  replicas: number;
  ready_replicas: number;
  component: string | null;
};

export type TenantSummary = {
  namespace: string;
  display_name: string;
  status: PodLifecycle;
  pod_count: number;
  is_lab_default: boolean;
  endpoints: EndpointInfo[];
};

export type TenantListResponse = {
  cluster_connected: boolean;
  cluster_error: string | null;
  lab_mode: boolean;
  lab_namespace: string;
  tenants: TenantSummary[];
};

export type TenantDetail = TenantSummary & {
  cluster_connected: boolean;
  pods: PodInfo[];
  deployments: DeploymentInfo[];
};

export type GameServerRate = {
  server_id: number;
  description: string | null;
  experience_rate: number;
};

export type GameRates = {
  experience_rate: number;
  master_experience_rate: number;
  maximum_level: number;
  maximum_master_level: number;
  maximum_item_option_level_drop: number;
  excellent_item_drop_level_delta: number;
  should_drop_money: boolean;
  item_drop_duration_seconds: number;
  game_servers: GameServerRate[];
  source: "postgresql" | "defaults";
  persisted: boolean;
  database_error: string | null;
};

export type DropGroup = {
  id: string;
  description: string | null;
  chance: number;
  minimum_monster_level: number | null;
  maximum_monster_level: number | null;
  item_type: number | null;
};

export type SpawnArea = {
  id: string;
  monster: string | null;
  map: string | null;
  quantity: number;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
};

export type GameEvent = {
  id: string;
  name: string | null;
  game_level: number | null;
  entrance_fee: number;
  maximum_player_count: number;
  minimum_character_level: number;
  maximum_character_level: number;
  allow_party: boolean;
};

export type ListEnvelope<T> = {
  items: T[];
  source: "postgresql" | "defaults";
  database_error: string | null;
};

export type ProvisionPayload = {
  server_name: string;
  display_name?: string;
  ports: { connect: number; game: number; chat: number; admin: number };
  database: { host?: string; name: string; user: string; password: string };
  replicas: 1;
};

export type ApiError = {
  detail: { code?: string; error?: string; hint?: string } | string;
};
