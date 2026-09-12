import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { api } from "./api";
import type {
  DropGroup,
  GameEvent,
  GameRates,
  HealthResponse,
  PodLifecycle,
  SpawnArea,
  TenantDetail,
  TenantListResponse,
} from "./types";

type Page = "status" | "rates" | "drops" | "spawns" | "events" | "provision";

const EMPTY_RATES: GameRates = {
  experience_rate: 1,
  master_experience_rate: 1,
  maximum_item_option_level_drop: 4,
  excellent_item_drop_level_delta: 25,
  should_drop_money: true,
  item_drop_duration_seconds: 60,
  source: "defaults",
  persisted: false,
  database_error: null,
};

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [tenants, setTenants] = useState<TenantListResponse | null>(null);
  const [detail, setDetail] = useState<TenantDetail | null>(null);
  const [page, setPage] = useState<Page>("status");
  const [flash, setFlash] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const labNs = health?.kubernetes.lab_namespace ?? "openmu-lab";

  const refresh = useCallback(async () => {
    const [h, list] = await Promise.all([api.health(), api.tenants()]);
    setHealth(h);
    setTenants(list);
    if (list.cluster_connected && list.tenants[0]) {
      try {
        setDetail(await api.tenant(list.tenants[0].namespace));
      } catch (err) {
        setDetail(null);
        setError(err instanceof Error ? err.message : String(err));
      }
    } else {
      setDetail(null);
    }
  }, []);

  useEffect(() => {
    refresh().catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, [refresh]);

  const namespace = detail?.namespace ?? labNs;

  return (
    <div className="shell">
      <aside>
        <div className="brand">
          <span className="mark">MU</span>
          <div>
            <strong>OpenMU</strong>
            <small>Lab control plane</small>
          </div>
        </div>
        <nav>
          {(
            [
              ["status", "Server status"],
              ["rates", "Rates"],
              ["drops", "Drops"],
              ["spawns", "Spawns"],
              ["events", "Events"],
              ["provision", "Provision"],
            ] as const
          ).map(([id, label]) => (
            <button key={id} className={page === id ? "active" : ""} onClick={() => setPage(id)}>
              {label}
            </button>
          ))}
        </nav>
        <div className="aside-meta">
          <StatusDot ok={Boolean(health?.kubernetes.connected)} label="Kubernetes" />
          <StatusDot ok={Boolean(health?.database.configured)} label="PostgreSQL" />
          <p className="hint">
            Tenant `{labNs}` · 1 replica
            {health?.kubernetes.api_server ? (
              <>
                <br />
                API {health.kubernetes.api_server}
              </>
            ) : null}
          </p>
        </div>
      </aside>
      <main>
        <header className="top">
          <div>
            <h1>{pageTitle(page)}</h1>
            <p>Single-tenant lab. Restart and provision stay inside `{namespace}`.</p>
          </div>
          <button className="ghost" onClick={() => void refresh()} disabled={busy}>
            Refresh
          </button>
        </header>
        {health && !health.kubernetes.connected && (
          <Banner tone="warn">
            No kubeconfig yet (set SAAS_KUBECONFIG). Intended lab API: {health.kubernetes.api_server}.{" "}
            {health.kubernetes.error}
          </Banner>
        )}
        {flash && <Banner tone="ok">{flash}</Banner>}
        {error && <Banner tone="bad">{error}</Banner>}

        {page === "status" && (
          <StatusPage
            tenants={tenants}
            detail={detail}
            namespace={namespace}
            busy={busy}
            onRestart={async (kind, name) => {
              setBusy(true);
              setError(null);
              setFlash(null);
              try {
                if (kind === "pod") await api.restartPod(namespace, name);
                else await api.restartDeployment(namespace, name);
                setFlash(`Restart requested for ${kind} ${name}.`);
                await refresh();
              } catch (err) {
                setError(err instanceof Error ? err.message : String(err));
              } finally {
                setBusy(false);
              }
            }}
          />
        )}
        {page === "rates" && <RatesPage namespace={namespace} onNotice={setFlash} onError={setError} />}
        {page === "drops" && <DropsPage namespace={namespace} onNotice={setFlash} onError={setError} />}
        {page === "spawns" && <SpawnsPage namespace={namespace} onNotice={setFlash} onError={setError} />}
        {page === "events" && <EventsPage namespace={namespace} onNotice={setFlash} onError={setError} />}
        {page === "provision" && (
          <ProvisionPage
            labNamespace={labNs}
            onNotice={setFlash}
            onError={setError}
          />
        )}
      </main>
    </div>
  );
}

function pageTitle(page: Page): string {
  switch (page) {
    case "status":
      return "Server status";
    case "rates":
      return "Experience & drop rates";
    case "drops":
      return "Drop groups";
    case "spawns":
      return "Monster spawns";
    case "events":
      return "Mini-game events";
    case "provision":
      return "Provision lab tenant";
  }
}

function StatusDot({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div className="dot-row">
      <span className={`dot ${ok ? "ok" : "off"}`} />
      {label}
    </div>
  );
}

function Banner({ tone, children }: { tone: "warn" | "ok" | "bad"; children: React.ReactNode }) {
  return <div className={`banner ${tone}`}>{children}</div>;
}

function StatusPage({
  tenants,
  detail,
  namespace,
  busy,
  onRestart,
}: {
  tenants: TenantListResponse | null;
  detail: TenantDetail | null;
  namespace: string;
  busy: boolean;
  onRestart: (kind: "pod" | "deployment", name: string) => void;
}) {
  const endpoints = detail?.endpoints?.length ? detail.endpoints : tenants?.tenants[0]?.endpoints ?? [];
  const pods = detail?.pods ?? [];
  const deployments = detail?.deployments ?? [];
  const status = detail?.status ?? tenants?.tenants[0]?.status ?? "Stopped";

  return (
    <>
      <section className="grid-2">
        <article className="card">
          <h2>Lab tenant</h2>
          <dl>
            <div>
              <dt>Namespace</dt>
              <dd>
                <code>{namespace}</code>
              </dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>
                <Pill status={status} />
              </dd>
            </div>
            <div>
              <dt>Pods</dt>
              <dd>{detail?.pod_count ?? 0}</dd>
            </div>
            <div>
              <dt>Cluster</dt>
              <dd>{tenants?.cluster_connected ? "connected" : "not connected"}</dd>
            </div>
          </dl>
        </article>
        <article className="card">
          <h2>Assigned IP / port</h2>
          {endpoints.length === 0 ? (
            <p className="muted">No Services yet. After Helm deploys the tenant, NodePort or LoadBalancer addresses show here.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Service</th>
                  <th>Address</th>
                  <th>Port</th>
                </tr>
              </thead>
              <tbody>
                {endpoints.map((ep) => (
                  <tr key={`${ep.name}-${ep.port}`}>
                    <td>
                      {ep.name}
                      {ep.component ? <small> · {ep.component}</small> : null}
                    </td>
                    <td>
                      <code>
                        {ep.ip ?? "—"}
                        {ep.node_port ? `:${ep.node_port}` : ep.port ? `:${ep.port}` : ""}
                      </code>
                    </td>
                    <td>
                      {ep.service_type}
                      {ep.note ? <small> · {ep.note}</small> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </article>
      </section>

      <article className="card">
        <h2>Deployments</h2>
        {deployments.length === 0 ? (
          <p className="muted">No deployments in `{namespace}`. Restart is disabled until the lab tenant exists.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Ready</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {deployments.map((d) => (
                <tr key={d.name}>
                  <td>{d.name}</td>
                  <td>
                    {d.ready_replicas}/{d.replicas}
                  </td>
                  <td>
                    <button disabled={busy} onClick={() => onRestart("deployment", d.name)}>
                      Restart
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </article>

      <article className="card">
        <h2>Pods</h2>
        {pods.length === 0 ? (
          <p className="muted">No OpenMU pods visible. The API returns a clear error if you still try to restart.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Pod</th>
                <th>Status</th>
                <th>Restarts</th>
                <th>Node</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {pods.map((p) => (
                <tr key={p.name}>
                  <td>
                    {p.name}
                    {p.reason ? <small> · {p.reason}</small> : null}
                  </td>
                  <td>
                    <Pill status={p.status} />
                  </td>
                  <td>{p.restarts}</td>
                  <td>{p.node ?? "—"}</td>
                  <td>
                    <button disabled={busy} onClick={() => onRestart("pod", p.name)}>
                      Restart
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </article>
    </>
  );
}

function Pill({ status }: { status: PodLifecycle }) {
  return <span className={`pill ${status.toLowerCase()}`}>{status}</span>;
}

function RatesPage({
  namespace,
  onNotice,
  onError,
}: {
  namespace: string;
  onNotice: (msg: string | null) => void;
  onError: (msg: string | null) => void;
}) {
  const [rates, setRates] = useState<GameRates>(EMPTY_RATES);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api
      .rates(namespace)
      .then(setRates)
      .catch((err: unknown) => onError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, [namespace, onError]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    onError(null);
    onNotice(null);
    try {
      const saved = await api.saveRates(namespace, rates);
      setRates(saved);
      onNotice("Rates saved in PostgreSQL. Restart the game deployment if the server caches config.");
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <form className="card form" onSubmit={(e) => void onSubmit(e)}>
      {loading && <p className="muted">Loading rates…</p>}
      {rates.database_error && <Banner tone="warn">{rates.database_error}</Banner>}
      <p className="muted">
        Source: {rates.source}
        {rates.persisted ? " (persisted)" : " (not written yet)"}
      </p>
      <label>
        Experience rate
        <input
          type="number"
          step="0.1"
          min={0.1}
          value={rates.experience_rate}
          onChange={(e) => setRates({ ...rates, experience_rate: Number(e.target.value) })}
        />
      </label>
      <label>
        Master experience rate
        <input
          type="number"
          step="0.1"
          min={0.1}
          value={rates.master_experience_rate}
          onChange={(e) => setRates({ ...rates, master_experience_rate: Number(e.target.value) })}
        />
      </label>
      <label>
        Max item option level drop
        <input
          type="number"
          min={0}
          max={15}
          value={rates.maximum_item_option_level_drop}
          onChange={(e) => setRates({ ...rates, maximum_item_option_level_drop: Number(e.target.value) })}
        />
      </label>
      <label>
        Excellent drop level delta
        <input
          type="number"
          min={0}
          max={255}
          value={rates.excellent_item_drop_level_delta}
          onChange={(e) => setRates({ ...rates, excellent_item_drop_level_delta: Number(e.target.value) })}
        />
      </label>
      <label>
        Item drop duration (seconds)
        <input
          type="number"
          min={1}
          value={rates.item_drop_duration_seconds}
          onChange={(e) => setRates({ ...rates, item_drop_duration_seconds: Number(e.target.value) })}
        />
      </label>
      <label className="check">
        <input
          type="checkbox"
          checked={rates.should_drop_money}
          onChange={(e) => setRates({ ...rates, should_drop_money: e.target.checked })}
        />
        Monsters drop zen on the ground
      </label>
      <button type="submit">Save rates</button>
    </form>
  );
}

function DropsPage({
  namespace,
  onNotice,
  onError,
}: {
  namespace: string;
  onNotice: (msg: string | null) => void;
  onError: (msg: string | null) => void;
}) {
  const [items, setItems] = useState<DropGroup[]>([]);
  const [warning, setWarning] = useState<string | null>(null);
  const [draft, setDraft] = useState({ id: "", chance: 0.01 });

  useEffect(() => {
    api
      .drops(namespace)
      .then((res) => {
        setItems(res.items);
        setWarning(res.database_error);
      })
      .catch((err: unknown) => onError(err instanceof Error ? err.message : String(err)));
  }, [namespace, onError]);

  return (
    <article className="card">
      {warning && <Banner tone="warn">{warning}</Banner>}
      {items.length === 0 ? (
        <p className="muted">No drop groups loaded. Connect tenant PostgreSQL to edit chances.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Description</th>
              <th>Chance</th>
            </tr>
          </thead>
          <tbody>
            {items.map((row) => (
              <tr key={row.id}>
                <td>{row.description || row.id}</td>
                <td>{(row.chance * 100).toFixed(2)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <form
        className="inline"
        onSubmit={(e) => {
          e.preventDefault();
          onError(null);
          api
            .saveDrop(namespace, draft.id, draft.chance)
            .then((saved) => {
              setItems((prev) => prev.map((x) => (x.id === saved.id ? saved : x)));
              onNotice(`Updated drop ${saved.id}.`);
            })
            .catch((err: unknown) => onError(err instanceof Error ? err.message : String(err)));
        }}
      >
        <label>
          Drop id
          <input value={draft.id} onChange={(e) => setDraft({ ...draft, id: e.target.value })} placeholder="uuid from the table" />
        </label>
        <label>
          Chance (0–1)
          <input
            type="number"
            step="0.001"
            min={0}
            max={1}
            value={draft.chance}
            onChange={(e) => setDraft({ ...draft, chance: Number(e.target.value) })}
          />
        </label>
        <button type="submit">Update drop</button>
      </form>
    </article>
  );
}

function SpawnsPage({
  namespace,
  onNotice,
  onError,
}: {
  namespace: string;
  onNotice: (msg: string | null) => void;
  onError: (msg: string | null) => void;
}) {
  const [items, setItems] = useState<SpawnArea[]>([]);
  const [warning, setWarning] = useState<string | null>(null);
  const [draft, setDraft] = useState({ id: "", quantity: 1 });

  useEffect(() => {
    api
      .spawns(namespace)
      .then((res) => {
        setItems(res.items);
        setWarning(res.database_error);
      })
      .catch((err: unknown) => onError(err instanceof Error ? err.message : String(err)));
  }, [namespace, onError]);

  return (
    <article className="card">
      {warning && <Banner tone="warn">{warning}</Banner>}
      {items.length === 0 ? (
        <p className="muted">No spawn areas loaded. Automatic map spawns appear here from `MonsterSpawnArea`.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Monster</th>
              <th>Map</th>
              <th>Qty</th>
              <th>Box</th>
            </tr>
          </thead>
          <tbody>
            {items.map((row) => (
              <tr key={row.id}>
                <td>{row.monster ?? row.id}</td>
                <td>{row.map ?? "—"}</td>
                <td>{row.quantity}</td>
                <td>
                  {row.x1}/{row.y1} → {row.x2}/{row.y2}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <form
        className="inline"
        onSubmit={(e) => {
          e.preventDefault();
          onError(null);
          api
            .saveSpawn(namespace, draft.id, draft.quantity)
            .then((saved) => {
              setItems((prev) => prev.map((x) => (x.id === saved.id ? saved : x)));
              onNotice(`Updated spawn ${saved.id} quantity to ${saved.quantity}.`);
            })
            .catch((err: unknown) => onError(err instanceof Error ? err.message : String(err)));
        }}
      >
        <label>
          Spawn id
          <input value={draft.id} onChange={(e) => setDraft({ ...draft, id: e.target.value })} placeholder="uuid" />
        </label>
        <label>
          Quantity
          <input
            type="number"
            min={0}
            max={500}
            value={draft.quantity}
            onChange={(e) => setDraft({ ...draft, quantity: Number(e.target.value) })}
          />
        </label>
        <button type="submit">Update spawn</button>
      </form>
    </article>
  );
}

function EventsPage({
  namespace,
  onNotice,
  onError,
}: {
  namespace: string;
  onNotice: (msg: string | null) => void;
  onError: (msg: string | null) => void;
}) {
  const [items, setItems] = useState<GameEvent[]>([]);
  const [warning, setWarning] = useState<string | null>(null);
  const [draft, setDraft] = useState({ id: "", entrance_fee: 0, maximum_player_count: 10 });

  useEffect(() => {
    api
      .events(namespace)
      .then((res) => {
        setItems(res.items);
        setWarning(res.database_error);
      })
      .catch((err: unknown) => onError(err instanceof Error ? err.message : String(err)));
  }, [namespace, onError]);

  return (
    <article className="card">
      {warning && <Banner tone="warn">{warning}</Banner>}
      {items.length === 0 ? (
        <p className="muted">No mini-game events loaded. Blood Castle / Devil Square rows come from `MiniGameDefinition`.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Event</th>
              <th>Level</th>
              <th>Fee</th>
              <th>Players</th>
            </tr>
          </thead>
          <tbody>
            {items.map((row) => (
              <tr key={row.id}>
                <td>{row.name ?? row.id}</td>
                <td>{row.game_level ?? "—"}</td>
                <td>{row.entrance_fee}</td>
                <td>{row.maximum_player_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <form
        className="inline"
        onSubmit={(e) => {
          e.preventDefault();
          onError(null);
          api
            .saveEvent(namespace, draft.id, {
              entrance_fee: draft.entrance_fee,
              maximum_player_count: draft.maximum_player_count,
            })
            .then((saved) => {
              setItems((prev) => prev.map((x) => (x.id === saved.id ? saved : x)));
              onNotice(`Updated event ${saved.name ?? saved.id}.`);
            })
            .catch((err: unknown) => onError(err instanceof Error ? err.message : String(err)));
        }}
      >
        <label>
          Event id
          <input value={draft.id} onChange={(e) => setDraft({ ...draft, id: e.target.value })} placeholder="uuid" />
        </label>
        <label>
          Entrance fee
          <input
            type="number"
            min={0}
            value={draft.entrance_fee}
            onChange={(e) => setDraft({ ...draft, entrance_fee: Number(e.target.value) })}
          />
        </label>
        <label>
          Max players
          <input
            type="number"
            min={1}
            max={500}
            value={draft.maximum_player_count}
            onChange={(e) => setDraft({ ...draft, maximum_player_count: Number(e.target.value) })}
          />
        </label>
        <button type="submit">Update event</button>
      </form>
    </article>
  );
}

function ProvisionPage({
  labNamespace,
  onNotice,
  onError,
}: {
  labNamespace: string;
  onNotice: (msg: string | null) => void;
  onError: (msg: string | null) => void;
}) {
  const [form, setForm] = useState({
    server_name: labNamespace,
    connect: 44405,
    game: 55901,
    chat: 55980,
    admin: 8080,
    db_name: "openmu",
    db_user: "postgres",
    db_password: "",
    db_host: "",
  });
  const preview = useMemo(
    () => ({
      namespace: labNamespace,
      replicas: 1,
      ports: `${form.connect}/${form.game}/${form.chat}/${form.admin}`,
    }),
    [form.admin, form.chat, form.connect, form.game, labNamespace],
  );

  return (
    <form
      className="card form"
      onSubmit={(e) => {
        e.preventDefault();
        onError(null);
        onNotice(null);
        api
          .provision({
            server_name: form.server_name,
            ports: { connect: form.connect, game: form.game, chat: form.chat, admin: form.admin },
            database: {
              host: form.db_host || undefined,
              name: form.db_name,
              user: form.db_user,
              password: form.db_password,
            },
            replicas: 1,
          })
          .then(() => onNotice("Unexpected success — Helm is still a stub."))
          .catch((err: unknown) => {
            const message = err instanceof Error ? err.message : String(err);
            onNotice(message);
          });
      }}
    >
      <Banner tone="warn">
        Lab mode: this will never create extra namespaces or more than 1 replica. Helm install is
        stubbed until `deploy/helm/` exists — the API only validates the request.
      </Banner>
      <label>
        Server name
        <input value={form.server_name} onChange={(e) => setForm({ ...form, server_name: e.target.value })} />
      </label>
      <p className="muted">
        Namespace pin: <code>{preview.namespace}</code> · replicas {preview.replicas} · ports {preview.ports}
      </p>
      <div className="grid-2">
        <label>
          Connect port
          <input type="number" value={form.connect} onChange={(e) => setForm({ ...form, connect: Number(e.target.value) })} />
        </label>
        <label>
          Game port
          <input type="number" value={form.game} onChange={(e) => setForm({ ...form, game: Number(e.target.value) })} />
        </label>
        <label>
          Chat port
          <input type="number" value={form.chat} onChange={(e) => setForm({ ...form, chat: Number(e.target.value) })} />
        </label>
        <label>
          Admin port
          <input type="number" value={form.admin} onChange={(e) => setForm({ ...form, admin: Number(e.target.value) })} />
        </label>
      </div>
      <label>
        PostgreSQL host (empty = in-cluster)
        <input value={form.db_host} onChange={(e) => setForm({ ...form, db_host: e.target.value })} placeholder="optional" />
      </label>
      <label>
        Database name
        <input value={form.db_name} onChange={(e) => setForm({ ...form, db_name: e.target.value })} />
      </label>
      <label>
        Database user
        <input value={form.db_user} onChange={(e) => setForm({ ...form, db_user: e.target.value })} />
      </label>
      <label>
        Database password
        <input
          type="password"
          value={form.db_password}
          onChange={(e) => setForm({ ...form, db_password: e.target.value })}
          required
          minLength={4}
        />
      </label>
      <button type="submit">Validate provision request</button>
    </form>
  );
}
