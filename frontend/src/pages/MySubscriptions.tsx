import { useEffect, useMemo, useState } from "react";
import { format, formatDistanceToNow } from "date-fns";
import { ru } from "date-fns/locale";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bell,
  Building2,
  Check,
  CheckCheck,
  Clock3,
  Copy,
  ExternalLink,
  FileWarning,
  Landmark,
  Loader2,
  MapPin,
  RefreshCw,
  Scale,
  Send,
  ShieldAlert,
  Sparkles,
  Trash2,
  Unlink,
  UserRound,
  WalletCards,
} from "lucide-react";

import { Footer } from "@/components/layout/Footer";
import { Header } from "@/components/layout/Header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/hooks/use-toast";
import {
  acknowledgeSubscriptionEvents,
  createTelegramLink,
  deleteSubscription,
  disconnectTelegram,
  EVENT_TYPE_LABELS,
  getCurrentUser,
  listSubscriptionEvents,
  listSubscriptions,
  logoutUser,
  type TelegramLinkResponse,
  type SubscriptionEventItem,
} from "@/lib/api";

const eventTone: Record<string, string> = {
  bankruptcy: "border-rose-500/25 bg-rose-500/10 text-rose-400",
  liquidation_started: "border-orange-500/25 bg-orange-500/10 text-orange-400",
  locked_supplier: "border-amber-500/25 bg-amber-500/10 text-amber-400",
  tax_debt: "border-red-500/25 bg-red-500/10 text-red-400",
  status_changed: "border-sky-500/25 bg-sky-500/10 text-sky-400",
  new_registration: "border-emerald-500/25 bg-emerald-500/10 text-emerald-400",
  egr_event: "border-cyan-500/25 bg-cyan-500/10 text-cyan-400",
  registry_appearance: "border-violet-500/25 bg-violet-500/10 text-violet-400",
};

const EventIcon = ({ type }: { type: string }) => {
  const className = "h-5 w-5";
  if (type === "bankruptcy") return <Scale className={className} />;
  if (type === "liquidation_started") return <FileWarning className={className} />;
  if (type === "locked_supplier") return <ShieldAlert className={className} />;
  if (type === "tax_debt") return <WalletCards className={className} />;
  if (type === "address_changed") return <MapPin className={className} />;
  if (type === "director_changed") return <UserRound className={className} />;
  if (type === "new_registration") return <Sparkles className={className} />;
  if (type === "registry_appearance") return <Landmark className={className} />;
  return <Bell className={className} />;
};

const formatEventDate = (value?: string | null) => {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return {
    relative: formatDistanceToNow(date, { addSuffix: true, locale: ru }),
    full: format(date, "d MMMM yyyy, HH:mm", { locale: ru }),
  };
};

const EventCard = ({
  event,
  onRead,
  isMarking,
}: {
  event: SubscriptionEventItem;
  onRead: (id: number) => void;
  isMarking: boolean;
}) => {
  const date = formatEventDate(event.occurred_at);
  const unread = !event.read_at;
  const tone = eventTone[event.event_type] ?? "border-primary/20 bg-primary/10 text-primary";

  return (
    <Card
      className={`surface-card overflow-hidden transition-all duration-300 ${
        unread ? "border-primary/25 shadow-[0_16px_50px_-32px_hsl(var(--primary)/0.65)]" : "opacity-80"
      }`}
    >
      <div className="relative p-4 sm:p-5">
        {unread && <span className="absolute right-4 top-4 h-2 w-2 rounded-full bg-primary shadow-[0_0_14px_hsl(var(--primary))]" />}
        <div className="flex items-start gap-3 sm:gap-4">
          <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border ${tone}`}>
            <EventIcon type={event.event_type} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 pr-5">
              <span className="font-semibold text-foreground">
                {EVENT_TYPE_LABELS[event.event_type] || event.event_type}
              </span>
              {unread && <Badge className="h-5 px-1.5 text-[10px]">Новое</Badge>}
            </div>
            <Link
              to={`/company/${event.unp}`}
              className="mt-1 block truncate text-sm text-muted-foreground transition-colors hover:text-primary"
            >
              {event.company_name || `Компания ${event.unp}`} · УНП {event.unp}
            </Link>

            {(event.old_value || event.new_value) && (
              <div className="mt-4 grid gap-2 sm:grid-cols-2">
                {event.old_value && (
                  <div className="rounded-lg border border-border/70 bg-background/40 px-3 py-2">
                    <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                      Было
                    </div>
                    <div className="break-words text-sm text-foreground/75">{event.old_value}</div>
                  </div>
                )}
                {event.new_value && (
                  <div className="rounded-lg border border-primary/20 bg-primary/[0.06] px-3 py-2">
                    <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-primary">
                      Стало
                    </div>
                    <div className="break-words text-sm text-foreground">{event.new_value}</div>
                  </div>
                )}
              </div>
            )}

            <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
              <span
                className="inline-flex items-center gap-1.5 text-xs text-muted-foreground"
                title={date?.full}
              >
                <Clock3 className="h-3.5 w-3.5" />
                {date?.relative || "Время не указано"}
              </span>
              {unread && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-8 gap-1.5 text-xs text-muted-foreground hover:text-foreground"
                  onClick={() => onRead(event.id)}
                  disabled={isMarking}
                >
                  <Check className="h-3.5 w-3.5" />
                  Прочитано
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>
    </Card>
  );
};

const MySubscriptions = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [scope, setScope] = useState<"all" | "unread">("all");
  const [eventType, setEventType] = useState("all");
  const [telegramLink, setTelegramLink] = useState<TelegramLinkResponse | null>(null);

  const meQuery = useQuery({ queryKey: ["me"], queryFn: getCurrentUser, retry: false });
  const telegramId = meQuery.data?.telegram_id;
  const refetchCurrentUser = meQuery.refetch;

  useEffect(() => {
    if (meQuery.isError) {
      navigate("/login?next=/subscriptions", { replace: true });
    }
  }, [meQuery.isError, navigate]);

  useEffect(() => {
    if (!telegramLink || telegramId) {
      return;
    }
    const interval = window.setInterval(() => {
      refetchCurrentUser();
    }, 5_000);
    return () => window.clearInterval(interval);
  }, [telegramLink, telegramId, refetchCurrentUser]);

  useEffect(() => {
    if (telegramId) {
      setTelegramLink(null);
    }
  }, [telegramId]);

  const subscriptionsQuery = useQuery({
    queryKey: ["subscriptions"],
    queryFn: listSubscriptions,
    enabled: !!meQuery.data,
    retry: false,
  });

  const eventsQuery = useQuery({
    queryKey: ["subscription-events", scope, eventType],
    queryFn: () =>
      listSubscriptionEvents({
        limit: 100,
        includeRead: scope === "all",
        newestFirst: true,
        eventType: eventType === "all" ? undefined : eventType,
      }),
    enabled: !!meQuery.data,
    retry: false,
    refetchInterval: 30_000,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteSubscription(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["subscriptions"] });
      toast({ title: "Подписка удалена" });
    },
    onError: (error: Error) =>
      toast({ title: "Ошибка", description: error.message, variant: "destructive" }),
  });

  const acknowledgeMutation = useMutation({
    mutationFn: (payload: { ids?: number[]; all?: boolean }) =>
      acknowledgeSubscriptionEvents(payload),
    onSuccess: ({ acknowledged }) => {
      queryClient.invalidateQueries({ queryKey: ["subscription-events"] });
      if (acknowledged > 1) {
        toast({ title: `Прочитано событий: ${acknowledged}` });
      }
    },
    onError: (error: Error) =>
      toast({ title: "Не удалось обновить ленту", description: error.message, variant: "destructive" }),
  });

  const telegramLinkMutation = useMutation({
    mutationFn: createTelegramLink,
    onSuccess: (result) => {
      setTelegramLink(result);
      if (result.linked) {
        queryClient.invalidateQueries({ queryKey: ["me"] });
      }
    },
    onError: (error: Error) =>
      toast({
        title: "Не удалось создать ссылку",
        description: error.message,
        variant: "destructive",
      }),
  });

  const disconnectTelegramMutation = useMutation({
    mutationFn: disconnectTelegram,
    onSuccess: () => {
      setTelegramLink(null);
      queryClient.invalidateQueries({ queryKey: ["me"] });
      toast({ title: "Telegram отключён" });
    },
    onError: (error: Error) =>
      toast({
        title: "Не удалось отключить Telegram",
        description: error.message,
        variant: "destructive",
      }),
  });

  const copyTelegramCommand = async () => {
    if (!telegramLink?.command) return;
    await navigator.clipboard.writeText(telegramLink.command);
    toast({ title: "Команда скопирована" });
  };

  const handleLogout = async () => {
    await logoutUser().catch(() => undefined);
    queryClient.clear();
    navigate("/", { replace: true });
  };

  const subscriptions = subscriptionsQuery.data?.items ?? [];
  const events = eventsQuery.data?.items ?? [];
  const unreadCount = eventsQuery.data?.unread_count ?? 0;
  const availableEventTypes = useMemo(
    () =>
      Object.entries(EVENT_TYPE_LABELS).sort(([, first], [, second]) =>
        first.localeCompare(second, "ru"),
      ),
    [],
  );
  const loading = meQuery.isLoading || subscriptionsQuery.isLoading;

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="mx-auto w-full max-w-6xl px-4 pb-16 pt-28 sm:pt-32">
        <div className="mb-7 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
          <div>
            <div className="mb-2 inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/[0.07] px-3 py-1 text-xs font-medium text-primary">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-primary" />
              Лента обновляется автоматически
            </div>
            <h1 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
              Центр событий
            </h1>
            <p className="mt-2 max-w-2xl text-sm text-muted-foreground sm:text-base">
              Изменения статусов, задолженности, банкротства и другие сигналы по компаниям,
              за которыми вы следите.
            </p>
          </div>
          <div className="flex items-center gap-2">
            {meQuery.data?.email && (
              <span className="hidden text-sm text-muted-foreground lg:inline">{meQuery.data.email}</span>
            )}
            <Button variant="outline" onClick={handleLogout}>Выйти</Button>
          </div>
        </div>

        {!loading && (
          <Card className="surface-card mb-5 overflow-hidden border-sky-500/20">
            <div className="flex flex-col gap-4 bg-gradient-to-r from-sky-500/[0.09] via-transparent to-primary/[0.06] p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5">
              <div className="flex items-start gap-3">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-sky-500/25 bg-sky-500/10 text-sky-400">
                  <Send className="h-5 w-5" />
                </div>
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="font-semibold text-foreground">Алерты в Telegram</h2>
                    {meQuery.data?.telegram_id ? (
                      <Badge className="border-emerald-500/25 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/10">
                        Подключено
                      </Badge>
                    ) : (
                      <Badge variant="secondary">Не подключено</Badge>
                    )}
                  </div>
                  <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
                    {meQuery.data?.telegram_id
                      ? "Изменения по вашим компаниям будут приходить в бот автоматически."
                      : "Подключите бот — банкротства, долги, статусы и другие изменения будут приходить сразу после обнаружения."}
                  </p>
                  {telegramLink?.command && !meQuery.data?.telegram_id && (
                    <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
                      {telegramLink.bot_url ? (
                        <Button asChild size="sm" className="gap-2">
                          <a href={telegramLink.bot_url} target="_blank" rel="noreferrer">
                            Открыть Telegram
                            <ExternalLink className="h-3.5 w-3.5" />
                          </a>
                        </Button>
                      ) : (
                        <code className="rounded-lg border border-border bg-background/60 px-3 py-2 text-xs text-foreground">
                          {telegramLink.command}
                        </code>
                      )}
                      <Button
                        variant="outline"
                        size="sm"
                        className="gap-2"
                        onClick={copyTelegramCommand}
                      >
                        <Copy className="h-3.5 w-3.5" />
                        Скопировать команду
                      </Button>
                      <span className="text-xs text-muted-foreground">
                        Ссылка действует 15 минут
                      </span>
                    </div>
                  )}
                </div>
              </div>

              {meQuery.data?.telegram_id ? (
                <Button
                  variant="outline"
                  className="shrink-0 gap-2"
                  onClick={() => disconnectTelegramMutation.mutate()}
                  disabled={disconnectTelegramMutation.isPending}
                >
                  <Unlink className="h-4 w-4" />
                  Отключить
                </Button>
              ) : (
                <Button
                  className="shrink-0 gap-2"
                  onClick={() => telegramLinkMutation.mutate()}
                  disabled={telegramLinkMutation.isPending}
                >
                  {telegramLinkMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Send className="h-4 w-4" />
                  )}
                  {telegramLink ? "Создать новую ссылку" : "Подключить Telegram"}
                </Button>
              )}
            </div>
          </Card>
        )}

        {loading ? (
          <div className="flex h-40 items-center justify-center text-muted-foreground">
            <Loader2 className="h-6 w-6 animate-spin" />
          </div>
        ) : (
          <Tabs defaultValue="events" className="space-y-5">
            <TabsList className="grid h-12 w-full grid-cols-2 rounded-xl sm:w-[420px]">
              <TabsTrigger value="events" className="h-10 gap-2 rounded-lg">
                <Bell className="h-4 w-4" />
                Лента событий
                {unreadCount > 0 && (
                  <span className="rounded-full bg-primary px-1.5 py-0.5 text-[10px] leading-none text-primary-foreground">
                    {unreadCount > 99 ? "99+" : unreadCount}
                  </span>
                )}
              </TabsTrigger>
              <TabsTrigger value="subscriptions" className="h-10 gap-2 rounded-lg">
                <Building2 className="h-4 w-4" />
                Подписки
                <span className="text-xs text-muted-foreground">{subscriptions.length}</span>
              </TabsTrigger>
            </TabsList>

            <TabsContent value="events" className="space-y-4">
              <Card className="surface-card">
                <div className="flex flex-col gap-4 p-4 lg:flex-row lg:items-center lg:justify-between">
                  <div className="flex items-center gap-3">
                    <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-primary/20 bg-primary/10 text-primary">
                      <Bell className="h-5 w-5" />
                    </div>
                    <div>
                      <div className="font-semibold text-foreground">
                        {unreadCount ? `${unreadCount} непрочитанных` : "Всё прочитано"}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        Показано {events.length} из {eventsQuery.data?.total_count ?? 0}
                      </div>
                    </div>
                  </div>

                  <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                    <div className="grid grid-cols-2 rounded-lg border border-border bg-background/40 p-1">
                      <Button
                        size="sm"
                        variant={scope === "all" ? "secondary" : "ghost"}
                        className="h-8"
                        onClick={() => setScope("all")}
                      >
                        Все
                      </Button>
                      <Button
                        size="sm"
                        variant={scope === "unread" ? "secondary" : "ghost"}
                        className="h-8"
                        onClick={() => setScope("unread")}
                      >
                        Непрочитанные
                      </Button>
                    </div>
                    <Select value={eventType} onValueChange={setEventType}>
                      <SelectTrigger className="w-full sm:w-[235px]">
                        <SelectValue placeholder="Тип события" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">Все типы событий</SelectItem>
                        {availableEventTypes.map(([value, label]) => (
                          <SelectItem key={value} value={value}>{label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Button
                      variant="outline"
                      size="icon"
                      onClick={() => eventsQuery.refetch()}
                      disabled={eventsQuery.isFetching}
                      aria-label="Обновить ленту"
                    >
                      <RefreshCw className={`h-4 w-4 ${eventsQuery.isFetching ? "animate-spin" : ""}`} />
                    </Button>
                    {unreadCount > 0 && (
                      <Button
                        variant="outline"
                        className="gap-2"
                        onClick={() => acknowledgeMutation.mutate({ all: true })}
                        disabled={acknowledgeMutation.isPending}
                      >
                        <CheckCheck className="h-4 w-4" />
                        Прочитать всё
                      </Button>
                    )}
                  </div>
                </div>
              </Card>

              {eventsQuery.isLoading && (
                <div className="flex h-32 items-center justify-center text-muted-foreground">
                  <Loader2 className="h-6 w-6 animate-spin" />
                </div>
              )}

              {eventsQuery.isError && (
                <Card className="surface-card border-destructive/25">
                  <div className="p-6 text-center">
                    <p className="text-sm text-destructive">Не удалось загрузить события.</p>
                    <Button variant="outline" className="mt-3" onClick={() => eventsQuery.refetch()}>
                      Повторить
                    </Button>
                  </div>
                </Card>
              )}

              {eventsQuery.data && events.length === 0 && (
                <Card className="surface-card">
                  <div className="flex flex-col items-center px-6 py-12 text-center">
                    <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl border border-primary/20 bg-primary/[0.07] text-primary">
                      <Bell className="h-6 w-6" />
                    </div>
                    <h2 className="font-semibold text-foreground">
                      {scope === "unread" ? "Новых событий нет" : "Лента пока пуста"}
                    </h2>
                    <p className="mt-2 max-w-md text-sm text-muted-foreground">
                      {subscriptions.length
                        ? "Когда данные по компаниям изменятся, событие появится здесь автоматически."
                        : "Откройте карточку компании и подпишитесь на интересующие изменения."}
                    </p>
                  </div>
                </Card>
              )}

              <div className="space-y-3">
                {events.map((event) => (
                  <EventCard
                    key={event.id}
                    event={event}
                    onRead={(id) => acknowledgeMutation.mutate({ ids: [id] })}
                    isMarking={acknowledgeMutation.isPending}
                  />
                ))}
              </div>

              {eventsQuery.data?.next_before_id && (
                <p className="text-center text-xs text-muted-foreground">
                  Показаны последние 100 событий. Уточните фильтр, чтобы найти более ранние.
                </p>
              )}
            </TabsContent>

            <TabsContent value="subscriptions">
              {subscriptions.length === 0 ? (
                <Card className="surface-card">
                  <div className="p-8 text-center text-muted-foreground">
                    У вас пока нет подписок. Откройте карточку компании и нажмите «Подписаться».
                  </div>
                </Card>
              ) : (
                <div className="grid gap-3 lg:grid-cols-2">
                  {subscriptions.map((subscription) => (
                    <Card key={subscription.id} className="surface-card">
                      <div className="flex items-start justify-between gap-3 p-4">
                        <div className="min-w-0">
                          <Link
                            to={`/company/${subscription.unp}`}
                            className="inline-flex items-center gap-2 font-medium text-foreground hover:text-primary"
                          >
                            <Building2 className="h-4 w-4 shrink-0 text-primary" />
                            <span>УНП {subscription.unp}</span>
                          </Link>
                          <div className="mt-3 flex flex-wrap gap-1.5">
                            {(subscription.event_types.length
                              ? subscription.event_types
                              : ["__all__"]
                            ).map((type) => (
                              <Badge key={type} variant="secondary" className="text-xs">
                                {type === "__all__"
                                  ? "Все события"
                                  : EVENT_TYPE_LABELS[type] || type}
                              </Badge>
                            ))}
                          </div>
                        </div>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="shrink-0 text-destructive hover:text-destructive"
                          onClick={() => deleteMutation.mutate(subscription.id)}
                          disabled={deleteMutation.isPending}
                          aria-label="Отписаться"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </Card>
                  ))}
                </div>
              )}
            </TabsContent>
          </Tabs>
        )}
      </main>
      <Footer />
    </div>
  );
};

export default MySubscriptions;
