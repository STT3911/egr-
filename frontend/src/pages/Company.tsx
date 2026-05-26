import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { motion } from "framer-motion";
import { AlertTriangle, ArrowLeft, Building2, CalendarDays, Database, ExternalLink, FileText, Globe, Info, Mail, Moon, Phone, Printer, Store, Sun } from "lucide-react";
import {
  getCompanyProfile,
  CompanyProfile,
  getGrpTaxpayerData,
  GrpTaxpayerData,
  getCompanyTaxDebt,
  CompanyTaxDebtResponse,
} from "@/lib/api";

const fieldLabels: Record<string, string> = {
  current_name_ru: "Полное название",
  current_short_name_ru: "Краткое название",
  current_name_by: "Название на белорусском",
  unp: "УНП",
  current_status_name: "Статус",
  registration_date: "Дата регистрации",
  liquidation_date: "Дата ликвидации",
  entity_type_id: "Тип субъекта",
  creation_method_id: "Способ создания",
  creation_decision_no: "Номер решения о создании",
  liquidation_decision_no: "Номер решения о ликвидации",
};

const cardReveal = {
  hidden: { opacity: 0, y: 18 },
  visible: { opacity: 1, y: 0 },
};

type TradeRegistryRecord = NonNullable<CompanyProfile["trade_registry_records"]>[number];

const Company = () => {
  const { unp } = useParams();
  const [profile, setProfile] = useState<CompanyProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [grpData, setGrpData] = useState<GrpTaxpayerData | null>(null);
  const [grpLoading, setGrpLoading] = useState(false);
  const [grpError, setGrpError] = useState<string | null>(null);
  const [taxDebtData, setTaxDebtData] = useState<CompanyTaxDebtResponse | null>(null);
  const [taxDebtLoading, setTaxDebtLoading] = useState(false);
  const [taxDebtError, setTaxDebtError] = useState<string | null>(null);
  const [activeItem, setActiveItem] = useState<string | null>(null);
  const [isDark, setIsDark] = useState(false);

  const handleItemClick = (itemId: string) => {
    setActiveItem(activeItem === itemId ? null : itemId);
  };

  useEffect(() => {
    const theme = localStorage.getItem("theme");
    const systemPrefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;

    if (theme === "dark" || (!theme && systemPrefersDark)) {
      setIsDark(true);
      document.documentElement.classList.add("dark");
    } else {
      setIsDark(false);
      document.documentElement.classList.remove("dark");
    }
  }, []);

  useEffect(() => {
    const load = async () => {
      if (!unp) {
        setError("УНП не указан");
        setLoading(false);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const data = await getCompanyProfile(unp);
        setProfile(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Ошибка загрузки профиля");
        setProfile(null);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [unp]);

  const loadGrp = async (forceRefresh = false) => {
    if (!unp) return;
    setGrpLoading(true);
    setGrpError(null);
    try {
      const data = await getGrpTaxpayerData(unp, forceRefresh);
      setGrpData(data);
    } catch (err) {
      setGrpError(err instanceof Error ? err.message : "Ошибка загрузки данных ГРП");
      setGrpData(null);
    } finally {
      setGrpLoading(false);
    }
  };

  useEffect(() => {
    // Load cached GRP record (if present). User can force refresh from UI.
    if (!unp) return;
    loadGrp(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unp]);

  useEffect(() => {
    const loadTaxDebt = async () => {
      if (!unp) return;
      setTaxDebtLoading(true);
      setTaxDebtError(null);
      try {
        const data = await getCompanyTaxDebt(unp);
        setTaxDebtData(data);
      } catch (err) {
        setTaxDebtError(
          err instanceof Error ? err.message : "Ошибка загрузки данных по налоговой задолженности"
        );
        setTaxDebtData(null);
      } finally {
        setTaxDebtLoading(false);
      }
    };

    loadTaxDebt();
  }, [unp]);

  const toggleTheme = () => {
    const newTheme = !isDark;
    setIsDark(newTheme);
    localStorage.setItem("theme", newTheme ? "dark" : "light");

    if (newTheme) {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  };

  const formatUpdatedAtUTC = (iso?: string) => {
    if (!iso) return "";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;

    return (
      new Intl.DateTimeFormat("ru-RU", {
        timeZone: "UTC",
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }).format(d) + " UTC"
    );
  };

  const formatDate = (value?: string) => {
    if (!value) return "—";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return value;
    return new Intl.DateTimeFormat("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    }).format(d);
  };

  const formatTradeAddress = (record: TradeRegistryRecord) => {
    return [
      record.object_region,
      record.object_district,
      record.object_locality,
      record.object_street,
      record.object_building,
      record.object_office,
    ].filter(Boolean).join(", ");
  };

  // Даты из bankrot могут быть 0001-01-01 — скрываем такие
  const formatBankrotDate = (value?: string) => {
    if (!value) return null;
    const d = new Date(value);
    if (Number.isNaN(d.getTime()) || d.getFullYear() < 1900) return null;
    return formatDate(value);
  };

  // Цвет индикатора статуса компании
  const statusIndicatorClass = (() => {
    const name = (profile?.current_status_name || "").toLowerCase();
    if (name.includes("ликвид") || name.includes("исключ") || name.includes("прекращ"))
      return "bg-red-500 shadow-[0_0_18px_hsl(0_72%_51%/0.5)]";
    if (name.includes("реорган") || name.includes("приостанов") || name.includes("процесс"))
      return "bg-yellow-500 shadow-[0_0_18px_hsl(45_93%_47%/0.5)]";
    return "bg-green-500 shadow-[0_0_18px_hsl(142_76%_36%/0.7)]";
  })();

  return (
    <div className="min-h-screen bg-background px-4 pb-12 pt-28 relative overflow-hidden" style={{
      background: 'linear-gradient(135deg, hsl(var(--background)) 0%, hsl(var(--background)) 70%, hsl(var(--secondary) / 0.2) 100%)'
    }}>

      {/* Floating Theme Toggle */}
      <button
        onClick={toggleTheme}
        className="fixed top-6 right-6 z-50 w-12 h-12 rounded-full glass shadow-card hover:shadow-glow transition-all duration-300 flex items-center justify-center"
        aria-label="Переключить тему"
      >
        {isDark ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
      </button>
      <div className="absolute inset-0 pointer-events-none registry-grid opacity-40" />
      {/* Background Decorative Elements */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="hidden sm:block absolute top-20 left-10 w-72 h-72 rounded-full blur-3xl animate-pulse dark:opacity-25" style={{
          backgroundColor: 'hsl(var(--primary) / 0.08)'
        }} />
        <div className="hidden sm:block absolute bottom-20 right-10 w-96 h-96 rounded-full blur-3xl animate-pulse dark:opacity-30" style={{
          backgroundColor: 'hsl(var(--accent) / 0.06)',
          animationDelay: "2s"
        }} />
        <div className="hidden lg:block absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] rounded-full blur-3xl dark:opacity-15" style={{
          backgroundColor: 'hsl(var(--primary) / 0.04)'
        }} />
        {/* Mobile decorative elements */}
        <div className="sm:hidden absolute top-10 right-10 w-32 h-32 rounded-full blur-2xl animate-pulse dark:opacity-20" style={{
          backgroundColor: 'hsl(var(--primary) / 0.06)'
        }} />
        <div className="sm:hidden absolute bottom-10 left-10 w-24 h-24 rounded-full blur-xl animate-pulse dark:opacity-25" style={{
          backgroundColor: 'hsl(var(--accent) / 0.05)',
          animationDelay: "1.5s"
        }} />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45 }}
        className="max-w-4xl mx-auto space-y-6 relative z-10"
      >
        {/* Back to Home Button */}
        <div className="flex items-center justify-start">
          <Link to="/">
            <Button variant="ghost" className="flex items-center gap-2 glass hover:bg-primary/10 dark:hover:bg-primary/20 transition-all duration-300">
              <ArrowLeft className="w-4 h-4" />
              На главную
            </Button>
          </Link>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="space-y-2">
            <h1 className="text-2xl sm:text-3xl md:text-4xl font-bold text-foreground leading-tight break-words">
              {profile?.current_name_ru || profile?.current_short_name_ru || "Профиль компании"}
            </h1>
            {unp && (
              <div className="flex items-center gap-2">
                <span className="glass px-3 py-1 rounded-full text-sm text-primary font-medium">
                  УНП {unp}
                </span>
              </div>
            )}
          </div>
          {unp && (
            <div className="flex gap-2 flex-wrap">
              <Link to={`/company/${unp}/raw`} className="flex-1 sm:flex-initial">
                <Button variant="outline" className="w-full sm:w-auto glass hover:bg-primary/10 dark:hover:bg-primary/20 transition-all duration-300 text-sm sm:text-base">
                  Raw данные
                </Button>
              </Link>
              <Link to={`/company/${unp}/compare`} className="flex-1 sm:flex-initial">
                <Button variant="outline" className="w-full sm:w-auto glass hover:bg-accent/10 dark:hover:bg-accent/20 transition-all duration-300 text-sm sm:text-base">
                  Сравнение API
                </Button>
              </Link>
            </div>
          )}
        </div>

        {loading && <p className="text-muted-foreground">Загрузка...</p>}
        {profile && (
          <motion.div
            variants={cardReveal}
            initial="hidden"
            animate="visible"
            transition={{ duration: 0.45, delay: 0.08 }}
            className="relative overflow-hidden rounded-2xl border border-primary/20 bg-card/80 shadow-card backdrop-blur-xl"
          >
            <div className="absolute inset-0 registry-grid opacity-30" />
            <motion.div
              className="absolute inset-y-0 -left-32 w-28 bg-gradient-to-r from-transparent via-primary/10 to-transparent"
              animate={{ x: ["0%", "950%"] }}
              transition={{ duration: 4.5, ease: "easeInOut", repeat: Infinity, repeatDelay: 3 }}
            />
            <div className="relative p-5 sm:p-6">
              <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
                <div className="space-y-3">
                  <div className="inline-flex items-center gap-2 rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
                    <Building2 className="h-3.5 w-3.5" />
                    Карточка компании
                  </div>
                  <div>
                    <div className="text-sm text-muted-foreground">Текущий статус</div>
                    <div className="mt-1 flex flex-wrap items-center gap-2">
                      <span className={`inline-flex h-2.5 w-2.5 rounded-full ${statusIndicatorClass}`} />
                      <span className="text-lg font-semibold text-foreground">
                        {profile.current_status_name || "Статус не указан"}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:min-w-[31rem]">
                  {[
                    { icon: Database, label: "УНП", value: profile.unp || unp || "—" },
                    { icon: CalendarDays, label: "Регистрация", value: formatDate(profile.registration_date) },
                    { icon: FileText, label: "Названий", value: profile.names?.length ?? 0 },
                    { icon: Building2, label: "Адресов", value: profile.addresses?.length ?? 0 },
                  ].map((item) => (
                    <motion.div
                      key={item.label}
                      whileHover={{ y: -4, scale: 1.02 }}
                      className="rounded-xl border border-border/70 bg-background/70 p-3 shadow-soft"
                    >
                      <item.icon className="mb-2 h-4 w-4 text-primary" />
                      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
                        {item.label}
                      </div>
                      <div className="mt-1 truncate text-sm font-semibold text-foreground">
                        {item.value}
                      </div>
                    </motion.div>
                  ))}
                </div>
              </div>
            </div>
          </motion.div>
        )}

        {error && (
          <Card className="border-destructive">
            <CardContent className="py-4 text-destructive">{error}</CardContent>
          </Card>
        )}

        {profile && (
          <motion.div
            variants={{
              visible: { transition: { staggerChildren: 0.08 } },
            }}
            initial="hidden"
            animate="visible"
            className="space-y-6"
          >
            <Card className="glass shadow-card hover:shadow-glow transition-all duration-300 border-primary/20">
              <CardHeader className="rounded-t-lg" style={{
                background: 'linear-gradient(90deg, hsl(var(--primary) / 0.1) 0%, hsl(var(--accent) / 0.1) 100%)'
              }}>
                <CardTitle className="text-foreground flex items-center gap-2 text-lg sm:text-xl">
                  <div className="w-2 h-2 rounded-full bg-primary animate-pulse"></div>
                  Основные данные
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 sm:space-y-4 p-4 sm:p-6">
                {Object.entries(fieldLabels).map(([key, label]) => {
                  const rawValue = (profile as Record<string, unknown>)[key];
                  if (rawValue === undefined || rawValue === null || rawValue === "") {
                    return null;
                  }
                  const value = typeof rawValue === "string" ? rawValue : String(rawValue);
                  return (
                    <div key={key} className="glass p-3 sm:p-4 rounded-lg hover:bg-primary/5 dark:hover:bg-primary/10 transition-all duration-300">
                      <span className="text-xs sm:text-sm text-muted-foreground font-medium block mb-1">{label}</span>
                      <span className="text-foreground font-semibold text-sm sm:text-base leading-relaxed">{value}</span>
                    </div>
                  );
                })}
              </CardContent>
            </Card>

          {/* История названий */}
          {profile.names && profile.names.length > 0 && (
            <Card className="glass shadow-card hover:shadow-glow transition-all duration-300 border-accent/20">
              <CardHeader className="rounded-t-lg" style={{
                background: 'linear-gradient(90deg, hsl(var(--accent) / 0.1) 0%, hsl(var(--primary) / 0.1) 100%)'
              }}>
                <CardTitle className="text-foreground flex items-center gap-2 text-lg sm:text-xl">
                  <div className="w-2 h-2 rounded-full bg-accent animate-pulse"></div>
                  История названий
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 sm:space-y-4 p-4 sm:p-6">
                <div className="text-xs text-muted-foreground text-center mb-4 opacity-60">
                  Наведите курсор или нажмите на запись для просмотра информации о датах
                </div>
                {profile.names.map((name, idx) => {
                  const itemId = `name-${idx}`;
                  return (
                    <div
                      key={idx}
                      className="glass p-3 sm:p-4 rounded-lg hover:bg-accent/5 dark:hover:bg-accent/10 transition-all duration-300 border-l-4 border-accent/30 group cursor-pointer relative"
                      onClick={() => handleItemClick(itemId)}
                    >
                      <div className="absolute top-2 sm:top-3 right-2 sm:right-3 opacity-40 group-hover:opacity-70 transition-opacity">
                        <div className="w-1.5 h-1.5 sm:w-2 sm:h-2 rounded-full bg-accent/50"></div>
                      </div>
                      <div className="space-y-2 pr-4 sm:pr-6">
                      {name.full_name_ru && (
                        <div>
                          <span className="text-xs sm:text-sm text-muted-foreground font-medium">Полное название:</span>
                          <p className="text-foreground font-semibold text-sm sm:text-base">{name.full_name_ru}</p>
                        </div>
                      )}
                      {name.short_name_ru && (
                        <div>
                          <span className="text-xs sm:text-sm text-muted-foreground font-medium">Краткое название:</span>
                          <p className="text-foreground font-semibold text-sm sm:text-base">{name.short_name_ru}</p>
                        </div>
                      )}
                      <div className={`transition-all duration-300 text-xs text-muted-foreground px-2 py-1 inline-block mt-2 ${
                        activeItem === itemId ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
                      }`}>
                        <div className="flex items-center gap-2">
                          <div className={`w-2 h-2 rounded-full ${!name.valid_to ? 'bg-green-500 animate-pulse' : 'bg-primary/60 dark:bg-primary/80'}`}></div>
                          <span>
                            {name.valid_from && `С ${name.valid_from}`}
                            {name.valid_to && ` по ${name.valid_to}`}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                  );
                })}
              </CardContent>
            </Card>
          )}

          {/* История адресов */}
          {profile.addresses && profile.addresses.length > 0 && (
            <Card className="glass shadow-card hover:shadow-glow transition-all duration-300 border-secondary/20">
              <CardHeader className="rounded-t-lg" style={{
                background: 'linear-gradient(90deg, hsl(var(--secondary) / 0.1) 0%, hsl(var(--primary) / 0.1) 100%)'
              }}>
                <CardTitle className="text-foreground flex items-center gap-2 text-lg sm:text-xl">
                  <div className="w-2 h-2 rounded-full bg-secondary animate-pulse"></div>
                  История адресов
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 sm:space-y-4 p-4 sm:p-6">
                <div className="text-xs text-muted-foreground text-center mb-4 opacity-60">
                  Наведите курсор или нажмите на адрес для просмотра периода действия
                </div>
                {profile.addresses.map((addr, idx) => {
                  const itemId = `address-${idx}`;
                  return (
                    <div
                      key={idx}
                      className="glass p-3 sm:p-4 rounded-lg hover:bg-secondary/5 dark:hover:bg-secondary/10 transition-all duration-300 border-l-4 border-secondary/30 group cursor-pointer relative"
                      onClick={() => handleItemClick(itemId)}
                    >
                      <div className="absolute top-2 sm:top-3 right-2 sm:right-3 opacity-40 group-hover:opacity-70 transition-opacity">
                        <div className="w-1.5 h-1.5 sm:w-2 sm:h-2 rounded-full bg-secondary/50"></div>
                      </div>
                      <p className="text-foreground font-semibold text-sm sm:text-base mb-2 pr-4 sm:pr-6">{addr.full_address}</p>
                    {(addr.region || addr.district) && (
                      <p className="text-xs sm:text-sm text-muted-foreground bg-primary/10 dark:bg-primary/20 px-2 py-1 rounded-full inline-block mb-2">
                        {[addr.region, addr.district].filter(Boolean).join(", ")}
                      </p>
                    )}
                    <div className={`transition-all duration-300 text-xs text-muted-foreground px-2 py-1 inline-block ${
                      activeItem === itemId ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
                    }`}>
                      <div className="flex items-center gap-2">
                          <div className={`w-2 h-2 rounded-full ${!addr.valid_to ? 'bg-green-500 animate-pulse' : 'bg-accent/60 dark:bg-accent/80'}`}></div>
                        <span>
                          {addr.valid_from && `С ${addr.valid_from}`}
                          {addr.valid_to && ` по ${addr.valid_to}`}
                        </span>
                      </div>
                    </div>
                  </div>
                  );
                })}

                {/* Legend */}
                <div className="mt-4 sm:mt-6 pt-3 sm:pt-4 border-t border-border/50">
                  <div className="flex flex-wrap items-center justify-center gap-3 sm:gap-4 text-xs text-muted-foreground">
                    <div className="flex items-center gap-2">
                      <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></div>
                      <span>Действует сейчас</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="w-2 h-2 rounded-full bg-accent/60 dark:bg-accent/80"></div>
                      <span>Архивная запись</span>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* История ВЭД */}
          {profile.ved && profile.ved.length > 0 && (
            <Card className="glass shadow-card hover:shadow-glow transition-all duration-300 border-primary/20">
              <CardHeader className="rounded-t-lg" style={{
                background: 'linear-gradient(90deg, hsl(var(--primary) / 0.1) 0%, hsl(var(--secondary) / 0.1) 100%)'
              }}>
                <CardTitle className="text-foreground flex items-center gap-2 text-lg sm:text-xl">
                  <div className="w-2 h-2 rounded-full bg-primary animate-pulse"></div>
                  Виды экономической деятельности
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 sm:space-y-4 p-4 sm:p-6">
                <div className="text-xs text-muted-foreground text-center mb-4 opacity-60">
                  Наведите курсор или нажмите на вид деятельности для просмотра периода действия
                </div>
                {profile.ved.map((v, idx) => {
                  const itemId = `ved-${idx}`;
                  return (
                    <div
                      key={idx}
                      className="glass p-3 sm:p-4 rounded-lg hover:bg-primary/5 dark:hover:bg-primary/10 transition-all duration-300 border-l-4 border-primary/30 group cursor-pointer relative"
                      onClick={() => handleItemClick(itemId)}
                    >
                      <div className="absolute top-2 sm:top-3 right-2 sm:right-3 opacity-40 group-hover:opacity-70 transition-opacity">
                        <div className="w-1.5 h-1.5 sm:w-2 sm:h-2 rounded-full bg-primary/50"></div>
                      </div>
                      <div className="flex flex-col sm:flex-row sm:gap-3 gap-2 items-start pr-4 sm:pr-6">
                      <span className="font-mono text-xs sm:text-sm glass px-2 py-1 rounded bg-primary/10 dark:bg-primary/20 text-primary font-semibold flex-shrink-0 w-fit">
                        {v.ved_code}
                      </span>
                      <span className="text-foreground font-medium flex-1 text-sm sm:text-base">{v.ved_name}</span>
                    </div>
                    <div className={`transition-all duration-300 text-xs text-muted-foreground px-2 py-1 inline-block mt-2 ${
                      activeItem === itemId ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
                    }`}>
                      <div className="flex items-center gap-2">
                        <div className={`w-2 h-2 rounded-full ${!v.valid_to ? 'bg-green-500 animate-pulse' : 'bg-secondary/60 dark:bg-secondary/80'}`}></div>
                        <span>
                          {v.valid_from && `С ${v.valid_from}`}
                          {v.valid_to && ` по ${v.valid_to}`}
                        </span>
                      </div>
                    </div>
                  </div>
                  );
                })}

                {/* Legend */}
                <div className="mt-4 sm:mt-6 pt-3 sm:pt-4 border-t border-border/50">
                  <div className="flex flex-wrap items-center justify-center gap-3 sm:gap-4 text-xs text-muted-foreground">
                    <div className="flex items-center gap-2">
                      <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></div>
                      <span>Действует сейчас</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="w-2 h-2 rounded-full bg-secondary/60 dark:bg-secondary/80"></div>
                      <span>Архивная запись</span>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Контактная информация */}
          {profile.contacts && profile.contacts.length > 0 && (
            <Card className="glass shadow-card hover:shadow-glow transition-all duration-300 border-accent/20">
              <CardHeader className="rounded-t-lg" style={{
                background: 'linear-gradient(90deg, hsl(var(--accent) / 0.1) 0%, hsl(var(--secondary) / 0.1) 100%)'
              }}>
                <CardTitle className="text-foreground flex items-center gap-2 text-lg sm:text-xl">
                  <div className="w-2 h-2 rounded-full bg-accent animate-pulse"></div>
                  Контактная информация
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 sm:space-y-4 p-4 sm:p-6">
                {profile.contacts.map((contact, idx) => (
                  <div key={idx} className="glass p-3 sm:p-4 rounded-lg hover:bg-accent/5 transition-all duration-300 space-y-2 sm:space-y-3">
                    {contact.phone && (
                      <div className="flex items-center gap-3">
                        <Phone className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                        <p className="text-foreground font-semibold text-sm sm:text-base break-all">{contact.phone}</p>
                      </div>
                    )}
                    {contact.fax && (
                      <div className="flex items-center gap-3">
                        <Printer className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                        <p className="text-foreground font-semibold text-sm sm:text-base break-all">{contact.fax}</p>
                      </div>
                    )}
                    {contact.email && (
                      <div className="flex items-center gap-3">
                        <Mail className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                        <p className="text-foreground font-semibold text-sm sm:text-base break-all">{contact.email}</p>
                      </div>
                    )}
                    {contact.website && (
                      <div className="flex items-center gap-3">
                        <Globe className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                        <a
                          href={contact.website}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-primary hover:text-primary/80 font-semibold underline decoration-primary/30 hover:decoration-primary transition-all duration-300 text-sm sm:text-base break-all"
                        >
                          {contact.website}
                        </a>
                      </div>
                    )}
                  </div>
                ))}

              </CardContent>
            </Card>
          )}

          {/* Примечание о реорганизованных органах */}
          <div className="glass p-3 sm:p-4 rounded-lg border-l-4 border-amber-500/50 text-xs sm:text-sm text-muted-foreground">
            <span className="inline-flex items-center gap-1.5 font-medium text-amber-600 dark:text-amber-400 mb-1">
              <Info className="w-3.5 h-3.5 flex-shrink-0" />
              Примечание:
            </span>{" "}
            Органы, отмеченные как «Реорганизованный орган», — это устаревшие регистрирующие органы (исполкомы, министерства),
            которые были реорганизованы или ликвидированы. Актуальные названия этих органов недоступны в данных ЕГР.
          </div>

          {/* Данные налоговой (GRP) */}
          <Card className="glass shadow-card hover:shadow-glow transition-all duration-300 border-primary/15">
            <CardHeader className="rounded-t-lg" style={{
              background: 'linear-gradient(90deg, hsl(var(--primary) / 0.08) 0%, hsl(var(--secondary) / 0.08) 100%)'
            }}>
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                <CardTitle className="text-foreground flex items-center gap-2 text-lg sm:text-xl">
                  <div className="w-2 h-2 rounded-full bg-primary animate-pulse"></div>
                  Данные налоговой
                </CardTitle>
                {unp && (
                  <Button
                    variant="outline"
                    className="w-full sm:w-auto glass hover:bg-primary/10 dark:hover:bg-primary/20 transition-all duration-300"
                    onClick={() => loadGrp(true)}
                    disabled={grpLoading}
                  >
                    {grpLoading ? "Обновление..." : "Обновить"}
                  </Button>
                )}
              </div>
            </CardHeader>
            <CardContent className="p-4 sm:p-6">
              {grpLoading && !grpData && (
                <p className="text-muted-foreground text-sm">Загрузка данных из налоговой...</p>
              )}

              {grpError && (
                <div className="glass p-3 rounded-lg border border-destructive/30 text-destructive text-sm mb-4">
                  {grpError}
                </div>
              )}

              {!grpLoading && !grpError && !grpData && (
                <p className="text-muted-foreground text-sm">
                  Данных пока нет. Нажмите «Обновить», чтобы подтянуть информацию из ГРП.
                </p>
              )}

              {grpData && (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <tbody className="divide-y divide-border/50">
                      <tr className="hover:bg-primary/5 transition-colors">
                        <td className="py-2 pr-4 text-muted-foreground whitespace-nowrap">Полное наименование</td>
                        <td className="py-2 font-medium text-foreground">{grpData.full_name || "—"}</td>
                      </tr>
                      <tr className="hover:bg-primary/5 transition-colors">
                        <td className="py-2 pr-4 text-muted-foreground whitespace-nowrap">Краткое наименование</td>
                        <td className="py-2 font-medium text-foreground">{grpData.short_name || "—"}</td>
                      </tr>
                      <tr className="hover:bg-primary/5 transition-colors">
                        <td className="py-2 pr-4 text-muted-foreground whitespace-nowrap">Дата регистрации</td>
                        <td className="py-2 font-medium text-foreground">{grpData.registration_date || "—"}</td>
                      </tr>
                      <tr className="hover:bg-primary/5 transition-colors">
                        <td className="py-2 pr-4 text-muted-foreground whitespace-nowrap">Инспекция</td>
                        <td className="py-2 font-medium text-foreground">
                          {grpData.inspectorate_name || (grpData.inspectorate_code ? `Код ${grpData.inspectorate_code}` : "—")}
                        </td>
                      </tr>
                      <tr className="hover:bg-primary/5 transition-colors">
                        <td className="py-2 pr-4 text-muted-foreground whitespace-nowrap">Код состояния</td>
                        <td className="py-2 font-medium text-foreground">{grpData.status_code || "—"}</td>
                      </tr>
                      <tr className="hover:bg-primary/5 transition-colors">
                        <td className="py-2 pr-4 text-muted-foreground whitespace-nowrap">Дата изменения состояния</td>
                        <td className="py-2 font-medium text-foreground">{grpData.status_date || "—"}</td>
                      </tr>
                      <tr className="hover:bg-primary/5 transition-colors">
                        <td className="py-2 pr-4 text-muted-foreground whitespace-nowrap">Адрес (ГРП)</td>
                        <td className="py-2 font-medium text-foreground">{grpData.address || "—"}</td>
                      </tr>
                    </tbody>
                  </table>

                  {grpData.last_error && (
                    <div className="mt-4 text-xs text-muted-foreground">
                      Последняя ошибка обновления: <span className="text-destructive">{grpData.last_error}</span>
                    </div>
                  )}
                  {grpData.updated_at && (
                    <div className="mt-1 text-xs text-muted-foreground">
                      Обновлено (UTC): {formatUpdatedAtUTC(grpData.updated_at)}
                    </div>
                  )}

                </div>
              )}
            </CardContent>
          </Card>

          {profile.pvt_resident && (
            <Card className="glass shadow-card hover:shadow-glow transition-all duration-300 border-primary/20">
              <CardHeader className="rounded-t-lg" style={{
                background: 'linear-gradient(90deg, hsl(var(--primary) / 0.1) 0%, hsl(var(--accent) / 0.08) 100%)'
              }}>
                <CardTitle className="text-foreground flex items-center gap-2 text-lg sm:text-xl">
                  <div className="w-2 h-2 rounded-full bg-primary animate-pulse"></div>
                  Резидент ПВТ
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 sm:space-y-4 p-4 sm:p-6">
                <div className="glass p-3 sm:p-4 rounded-lg space-y-3">
                  <div>
                    <span className="text-xs sm:text-sm text-muted-foreground font-medium block mb-1">Наименование</span>
                    <p className="text-foreground font-semibold text-sm sm:text-base">
                      {profile.pvt_resident.name || profile.current_short_name_ru || profile.current_name_ru || "—"}
                    </p>
                  </div>
                  {profile.pvt_resident.description && (
                    <div>
                      <span className="text-xs sm:text-sm text-muted-foreground font-medium block mb-1">Описание</span>
                      <p className="text-foreground text-sm sm:text-base leading-relaxed">
                        {profile.pvt_resident.description}
                      </p>
                    </div>
                  )}
                  {profile.pvt_resident.profile_url && (
                    <a
                      href={profile.pvt_resident.profile_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-2 text-primary hover:text-primary/80 font-semibold underline decoration-primary/30 hover:decoration-primary transition-all duration-300 text-sm"
                    >
                      <ExternalLink className="h-4 w-4" />
                      Профиль на park.by
                    </a>
                  )}
                  {profile.pvt_resident.last_seen_at && (
                    <div className="text-xs text-muted-foreground">
                      Обновлено (UTC): {formatUpdatedAtUTC(profile.pvt_resident.last_seen_at)}
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          )}

          {profile.trade_registry_records && profile.trade_registry_records.length > 0 && (
            <Card className="glass shadow-card hover:shadow-glow transition-all duration-300 border-accent/20">
              <CardHeader className="rounded-t-lg" style={{
                background: 'linear-gradient(90deg, hsl(var(--accent) / 0.1) 0%, hsl(var(--primary) / 0.08) 100%)'
              }}>
                <CardTitle className="text-foreground flex items-center gap-2 text-lg sm:text-xl">
                  <Store className="w-5 h-5 text-accent" />
                  Торговый реестр МАРТ
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 sm:space-y-4 p-4 sm:p-6">
                <div className="text-sm text-muted-foreground">
                  Записей: {profile.trade_registry_records.length}
                </div>
                {profile.trade_registry_records.map((record, idx) => {
                  const address = formatTradeAddress(record);
                  const title = record.object_name || record.internet_shop_domain || record.trade_network_name || record.object_type || `Запись ${idx + 1}`;
                  return (
                    <div key={`${record.registration_number}-${idx}`} className="glass p-3 sm:p-4 rounded-lg hover:bg-accent/5 transition-all duration-300 space-y-3">
                      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2">
                        <div>
                          <span className="text-xs sm:text-sm text-muted-foreground font-medium block mb-1">Объект</span>
                          <p className="text-foreground font-semibold text-sm sm:text-base leading-relaxed">{title}</p>
                        </div>
                        {record.registration_number && (
                          <span className="font-mono text-xs glass px-2 py-1 rounded bg-accent/10 text-accent font-semibold w-fit">
                            № {record.registration_number}
                          </span>
                        )}
                      </div>

                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                        {record.object_type && (
                          <div>
                            <span className="text-muted-foreground block">Тип</span>
                            <span className="text-foreground font-medium">{record.object_type}</span>
                          </div>
                        )}
                        {record.format_type && (
                          <div>
                            <span className="text-muted-foreground block">Формат</span>
                            <span className="text-foreground font-medium">{record.format_type}</span>
                          </div>
                        )}
                        {record.trade_object_type && (
                          <div>
                            <span className="text-muted-foreground block">Вид объекта</span>
                            <span className="text-foreground font-medium">{record.trade_object_type}</span>
                          </div>
                        )}
                        {record.trade_area && (
                          <div>
                            <span className="text-muted-foreground block">Торговая площадь</span>
                            <span className="text-foreground font-medium">{record.trade_area}</span>
                          </div>
                        )}
                        {record.inclusion_date && (
                          <div>
                            <span className="text-muted-foreground block">Дата включения</span>
                            <span className="text-foreground font-medium">{formatDate(record.inclusion_date)}</span>
                          </div>
                        )}
                        {record.source_date && (
                          <div>
                            <span className="text-muted-foreground block">Срез МАРТ</span>
                            <span className="text-foreground font-medium">{formatDate(record.source_date)}</span>
                          </div>
                        )}
                      </div>

                      {address && (
                        <div className="text-sm">
                          <span className="text-muted-foreground block">Адрес объекта</span>
                          <span className="text-foreground font-medium">{address}</span>
                        </div>
                      )}
                      {record.internet_shop_domain && (
                        <div className="text-sm">
                          <span className="text-muted-foreground block">Интернет-магазин</span>
                          <span className="text-foreground font-medium break-all">{record.internet_shop_domain}</span>
                        </div>
                      )}
                      {record.goods_groups && (
                        <div className="text-sm">
                          <span className="text-muted-foreground block">Группы товаров</span>
                          <span className="text-foreground font-medium">{record.goods_groups}</span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </CardContent>
            </Card>
          )}

          {/* Банкротство */}
          {profile.bankrot_cases && profile.bankrot_cases.length > 0 && (
            <Card className="glass shadow-card hover:shadow-glow transition-all duration-300 border-orange-500/30">
              <CardHeader className="rounded-t-lg" style={{
                background: 'linear-gradient(90deg, hsl(25 95% 53% / 0.12) 0%, hsl(var(--destructive) / 0.08) 100%)'
              }}>
                <CardTitle className="text-foreground flex items-center gap-2 text-lg sm:text-xl">
                  <AlertTriangle className="w-5 h-5 text-orange-500" />
                  Банкротство
                  <span className="ml-auto text-sm font-normal text-muted-foreground">
                    {profile.bankrot_cases.length} {profile.bankrot_cases.length === 1 ? "дело" : profile.bankrot_cases.length < 5 ? "дела" : "дел"}
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 sm:space-y-4 p-4 sm:p-6">
                {profile.bankrot_cases.map((c) => {
                  const isActive = !c.end_date;
                  return (
                    <div key={c.case_id} className={`glass p-3 sm:p-4 rounded-lg transition-all duration-300 border-l-4 space-y-3 ${
                      isActive ? "border-orange-500/60 hover:bg-orange-500/5" : "border-border/50 hover:bg-muted/30"
                    }`}>
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex items-center gap-2 flex-wrap">
                          {c.number && (
                            <span className="font-mono text-xs glass px-2 py-1 rounded bg-orange-500/10 text-orange-600 dark:text-orange-400 font-semibold">
                              № {c.number}
                            </span>
                          )}
                          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                            isActive
                              ? "bg-orange-500/15 text-orange-600 dark:text-orange-400"
                              : "bg-muted text-muted-foreground"
                          }`}>
                            {isActive ? "● Активное" : "✓ Завершено"}
                          </span>
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {formatBankrotDate(c.start_date) && <span>с {formatBankrotDate(c.start_date)}</span>}
                          {formatBankrotDate(c.end_date) && <span> по {formatBankrotDate(c.end_date)}</span>}
                        </div>
                      </div>

                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
                        {c.court && (
                          <div>
                            <span className="text-xs text-muted-foreground block">Суд</span>
                            <span className="text-foreground font-medium">{c.court}</span>
                          </div>
                        )}
                        {c.judge && (
                          <div>
                            <span className="text-xs text-muted-foreground block">Судья</span>
                            <span className="text-foreground font-medium">{c.judge}</span>
                          </div>
                        )}
                        {c.manager_name && (
                          <div className="sm:col-span-2">
                            <span className="text-xs text-muted-foreground block">Управляющий</span>
                            <span className="text-foreground font-medium">{c.manager_name}</span>
                          </div>
                        )}
                      </div>

                      {c.updated_at && (
                        <div className="text-xs text-muted-foreground">
                          Обновлено: {formatUpdatedAtUTC(c.updated_at)}
                        </div>
                      )}
                    </div>
                  );
                })}
              </CardContent>
            </Card>
          )}

          <Card className="glass shadow-card hover:shadow-glow transition-all duration-300 border-destructive/20">
            <CardHeader
              className="rounded-t-lg"
              style={{
                background: "linear-gradient(90deg, hsl(var(--destructive) / 0.08) 0%, hsl(var(--primary) / 0.08) 100%)",
              }}
            >
              <CardTitle className="text-foreground flex items-center gap-2 text-lg sm:text-xl">
                <div className="w-2 h-2 rounded-full bg-destructive animate-pulse"></div>
                Налоговая задолженность
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4 sm:p-6">
              {taxDebtLoading && !taxDebtData && (
                <p className="text-muted-foreground text-sm">Загрузка данных о задолженности...</p>
              )}

              {taxDebtError && (
                <div className="glass p-3 rounded-lg border border-destructive/30 text-destructive text-sm mb-4">
                  {taxDebtError}
                </div>
              )}

              {!taxDebtLoading && !taxDebtError && taxDebtData && taxDebtData.count === 0 && (
                <div className="space-y-2">
                  <p className="text-muted-foreground text-sm">
                    Записей о налоговой задолженности по этой компании сейчас нет.
                  </p>
                </div>
              )}

              {taxDebtData && taxDebtData.count > 0 && (
                <div className="space-y-4">
                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 text-sm">
                    <div className="text-foreground font-medium">
                      Найдено записей: {taxDebtData.count}
                    </div>
                    <div className="text-muted-foreground">
                      Последний срез: {formatDate(taxDebtData.latest_slice_date)}
                    </div>
                  </div>

                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left text-muted-foreground border-b border-border/50">
                          <th className="py-2 pr-4 whitespace-nowrap">ИМНС</th>
                          <th className="py-2 pr-4 whitespace-nowrap">Дата задолженности</th>
                          <th className="py-2 pr-4 whitespace-nowrap">Дата погашения</th>
                          <th className="py-2 whitespace-nowrap">Срез</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border/50">
                        {taxDebtData.items.map((item, idx) => (
                          <tr key={`${item.imns_code}-${item.debt_date}-${item.slice_date}-${idx}`} className="hover:bg-destructive/5 transition-colors">
                            <td className="py-2 pr-4 text-foreground">
                              {item.imns_name || `Код ${item.imns_code}`}
                            </td>
                            <td className="py-2 pr-4 text-foreground">{item.debt_date || "—"}</td>
                            <td className="py-2 pr-4 text-foreground">{item.repayment_date || "—"}</td>
                            <td className="py-2 text-foreground">{formatDate(item.slice_date)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
          </motion.div>
        )}
      </motion.div>
    </div>
  );
};

export default Company;
