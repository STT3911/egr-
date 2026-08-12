import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowLeft,
  Building2,
  ExternalLink,
  Loader2,
  Mail,
  MapPin,
  Network,
  Phone,
  type LucideIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  CompanyRelationEdge,
  CompanyRelationGraph,
  CompanyRelationNode,
  getCompanyRelationGraph,
} from "@/lib/api";

type RelationFilter = "all" | CompanyRelationEdge["type"];
type PositionedNode = CompanyRelationNode & { x: number; y: number };

const relationMeta = {
  phone: { label: "Телефон", color: "#0ea5e9", Icon: Phone },
  email: { label: "Email", color: "#8b5cf6", Icon: Mail },
  address: { label: "Адрес", color: "#f59e0b", Icon: MapPin },
};

const positionRing = (
  nodes: CompanyRelationNode[],
  radiusX: number,
  radiusY: number,
  centerX: number,
  centerY: number,
  phase = 0
) =>
  nodes.map((node, index) => {
    const angle = phase + (Math.PI * 2 * index) / Math.max(nodes.length, 1);
    return {
      ...node,
      x: centerX + Math.cos(angle) * radiusX,
      y: centerY + Math.sin(angle) * radiusY,
    };
  });

const CompanyRelations = () => {
  const { unp = "" } = useParams();
  const [graph, setGraph] = useState<CompanyRelationGraph | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<RelationFilter>("all");
  const [selectedUnp, setSelectedUnp] = useState<number | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    getCompanyRelationGraph(unp)
      .then((data) => {
        if (!active) return;
        setGraph(data);
        setSelectedUnp(data.root_unp);
      })
      .catch((reason: Error) => {
        if (active) setError(reason.message || "Не удалось построить карту связей");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [unp]);

  const positionedNodes = useMemo(() => {
    if (!graph) return [];
    const root = graph.nodes.find((node) => node.depth === 0);
    const direct = graph.nodes.filter((node) => node.depth === 1);
    const indirect = graph.nodes.filter((node) => node.depth === 2);
    const result: PositionedNode[] = [];
    if (root) result.push({ ...root, x: 450, y: 360 });
    result.push(...positionRing(direct, 210, 170, 450, 360, -Math.PI / 2));
    result.push(...positionRing(indirect, 385, 300, 450, 360, -Math.PI / 2));
    return result;
  }, [graph]);

  const nodePositions = useMemo(
    () => new Map(positionedNodes.map((node) => [node.unp, node])),
    [positionedNodes]
  );

  const visibleEdges = useMemo(
    () => graph?.edges.filter((edge) => filter === "all" || edge.type === filter) || [],
    [filter, graph]
  );

  const connectedUnps = useMemo(() => {
    if (filter === "all") return new Set(positionedNodes.map((node) => node.unp));
    return new Set(visibleEdges.flatMap((edge) => [edge.source_unp, edge.target_unp]));
  }, [filter, positionedNodes, visibleEdges]);

  const selectedNode = graph?.nodes.find((node) => node.unp === selectedUnp) || null;
  const selectedEdges = graph?.edges.filter(
    (edge) => edge.source_unp === selectedUnp || edge.target_unp === selectedUnp
  ) || [];

  return (
    <div className="min-h-screen bg-background px-4 py-8">
      <div className="mx-auto max-w-7xl space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Link to={`/company/${unp}`}>
            <Button variant="ghost" className="gap-2">
              <ArrowLeft className="h-4 w-4" />
              К карточке компании
            </Button>
          </Link>
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Network className="h-4 w-4 text-primary" />
            Прямые и косвенные связи, глубина 2
          </div>
        </div>

        <div>
          <h1 className="text-3xl font-bold text-foreground">Карта связей компании</h1>
          <p className="mt-2 text-muted-foreground">
            Общие телефоны, email и адреса между контрагентами. УНП {unp}
          </p>
        </div>

        {loading && (
          <Card>
            <CardContent className="flex min-h-[520px] items-center justify-center gap-3 text-muted-foreground">
              <Loader2 className="h-6 w-6 animate-spin text-primary" />
              Строим сеть связей…
            </CardContent>
          </Card>
        )}

        {error && (
          <Card className="border-destructive/40">
            <CardContent className="flex items-center gap-3 py-6 text-destructive">
              <AlertTriangle className="h-5 w-5" />
              {error}
            </CardContent>
          </Card>
        )}

        {graph && !loading && (
          <>
            <Card className="overflow-hidden">
              <CardContent className="grid grid-cols-2 gap-px bg-border/60 p-0 sm:grid-cols-3 lg:grid-cols-5">
                {[
                  { label: "Компаний", value: graph.stats.companies, Icon: Building2 },
                  { label: "Связей", value: graph.stats.connections, Icon: Network },
                  { label: "Телефоны", value: graph.stats.phones, Icon: Phone },
                  { label: "Email", value: graph.stats.emails, Icon: Mail },
                  { label: "Адреса", value: graph.stats.addresses, Icon: MapPin },
                ].map(({ label, value, Icon }: { label: string; value: number; Icon: LucideIcon }) => (
                  <div
                    key={label}
                    className="flex min-w-0 items-center gap-3 bg-card p-4 sm:p-5"
                  >
                    <div className="shrink-0 rounded-xl bg-primary/10 p-2.5">
                      <Icon className="h-5 w-5 text-primary" />
                    </div>
                    <div className="min-w-0">
                      <div className="text-2xl font-bold leading-none">{value}</div>
                      <div className="mt-1 truncate text-xs text-muted-foreground">{label}</div>
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>

            <div className="grid min-w-0 items-start gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
              <Card className="min-w-0 overflow-hidden">
                <CardHeader className="border-b border-border/60">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <CardTitle className="text-lg">Сеть контрагентов</CardTitle>
                    <div className="flex flex-wrap gap-2">
                      {(["all", "phone", "email", "address"] as RelationFilter[]).map((type) => {
                        const label = type === "all" ? "Все" : relationMeta[type].label;
                        return (
                          <Button
                            key={type}
                            size="sm"
                            variant={filter === type ? "default" : "outline"}
                            onClick={() => setFilter(type)}
                          >
                            {label}
                          </Button>
                        );
                      })}
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="min-w-0 max-w-full overflow-x-auto p-0">
                  {graph.nodes.length === 1 ? (
                    <div className="flex min-h-[520px] items-center justify-center px-6 text-center text-muted-foreground">
                      Связи по общим контактам и адресам не найдены
                    </div>
                  ) : (
                    <svg viewBox="0 0 900 720" className="block h-auto min-h-[560px] min-w-[760px] max-w-none bg-muted/10">
                      <defs>
                        <filter id="node-shadow" x="-50%" y="-50%" width="200%" height="200%">
                          <feDropShadow dx="0" dy="3" stdDeviation="4" floodOpacity="0.18" />
                        </filter>
                      </defs>
                      {visibleEdges.map((edge, index) => {
                        const source = nodePositions.get(edge.source_unp);
                        const target = nodePositions.get(edge.target_unp);
                        if (!source || !target) return null;
                        return (
                          <line
                            key={`${edge.source_unp}-${edge.target_unp}-${edge.type}-${index}`}
                            x1={source.x}
                            y1={source.y}
                            x2={target.x}
                            y2={target.y}
                            stroke={relationMeta[edge.type].color}
                            strokeWidth={edge.source_unp === selectedUnp || edge.target_unp === selectedUnp ? 3 : 1.7}
                            strokeOpacity={edge.source_unp === selectedUnp || edge.target_unp === selectedUnp ? 0.9 : 0.45}
                          />
                        );
                      })}
                      {positionedNodes.map((node) => {
                        const active = selectedUnp === node.unp;
                        const visible = connectedUnps.has(node.unp);
                        const radius = node.depth === 0 ? 28 : node.depth === 1 ? 19 : 14;
                        return (
                          <g
                            key={node.unp}
                            onClick={() => setSelectedUnp(node.unp)}
                            className="cursor-pointer"
                            opacity={visible ? 1 : 0.18}
                          >
                            <circle
                              cx={node.x}
                              cy={node.y}
                              r={radius + (active ? 5 : 0)}
                              fill={node.depth === 0 ? "hsl(var(--primary))" : "hsl(var(--card))"}
                              stroke={active ? "hsl(var(--primary))" : "hsl(var(--border))"}
                              strokeWidth={active ? 4 : 2}
                              filter="url(#node-shadow)"
                            />
                            <text
                              x={node.x}
                              y={node.y + 4}
                              textAnchor="middle"
                              fontSize={node.depth === 0 ? 12 : 9}
                              fontWeight="700"
                              fill={node.depth === 0 ? "white" : "currentColor"}
                            >
                              {String(node.unp).slice(-4)}
                            </text>
                            {node.depth < 2 && (
                              <text
                                x={node.x}
                                y={node.y + radius + 18}
                                textAnchor="middle"
                                fontSize="10"
                                fill="hsl(var(--muted-foreground))"
                              >
                                {node.name && node.name.length > 24 ? `${node.name.slice(0, 24)}…` : node.name || node.unp}
                              </text>
                            )}
                          </g>
                        );
                      })}
                    </svg>
                  )}
                </CardContent>
              </Card>

              <Card className="h-fit min-w-0 xl:sticky xl:top-6">
                <CardHeader>
                  <CardTitle className="text-lg">Выбранная компания</CardTitle>
                </CardHeader>
                <CardContent className="space-y-5">
                  {selectedNode && (
                    <>
                      <div>
                        <div className="break-words font-semibold leading-snug">
                          {selectedNode.name || `Компания ${selectedNode.unp}`}
                        </div>
                        <div className="mt-1 font-mono text-sm text-muted-foreground">
                          УНП {selectedNode.unp}
                        </div>
                        <div className="mt-2 text-xs text-muted-foreground">
                          {selectedNode.depth === 0
                            ? "Исходная компания"
                            : selectedNode.depth === 1
                              ? "Прямая связь"
                              : "Связь второго уровня"}
                        </div>
                      </div>
                      <Link to={`/company/${selectedNode.unp}`}>
                        <Button className="w-full gap-2">
                          Открыть карточку <ExternalLink className="h-4 w-4" />
                        </Button>
                      </Link>
                      <div className="space-y-2 border-t border-border/60 pt-4">
                        <div className="text-sm font-medium">Найденные связи</div>
                        {selectedEdges.length === 0 && (
                          <div className="text-sm text-muted-foreground">Нет связей</div>
                        )}
                        {selectedEdges.slice(0, 12).map((edge, index) => {
                          const meta = relationMeta[edge.type];
                          const relatedUnp = edge.source_unp === selectedNode.unp
                            ? edge.target_unp
                            : edge.source_unp;
                          return (
                            <button
                              key={`${edge.type}-${relatedUnp}-${index}`}
                              type="button"
                              onClick={() => setSelectedUnp(relatedUnp)}
                              className="w-full min-w-0 rounded-xl border border-border/60 p-3 text-left transition-colors hover:bg-muted/50"
                            >
                              <div className="flex items-center gap-2 text-xs font-medium" style={{ color: meta.color }}>
                                <meta.Icon className="h-3.5 w-3.5" />
                                {meta.label} · УНП {relatedUnp}
                              </div>
                              <div className="mt-1 truncate text-xs text-muted-foreground" title={edge.value || undefined}>
                                {edge.value || "Совпадение"}
                              </div>
                            </button>
                          );
                        })}
                      </div>
                    </>
                  )}
                </CardContent>
              </Card>
            </div>

            {graph.truncated && (
              <div className="flex min-w-0 items-start gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-700 dark:text-amber-300">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>Показаны 40 наиболее близких компаний. Сеть содержит больше связей.</span>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default CompanyRelations;
