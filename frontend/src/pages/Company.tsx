import React, { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CompanyMap } from "@/components/CompanyMap";
import { BankrotDataView } from "@/components/bankrot/BankrotDataView";
import { GiasContractsSection } from "@/components/gias/GiasContractsSection";
import { GiasBankAccountsSection } from "@/components/gias/GiasBankAccountsSection";
import { getBankrotPayloadCount } from "@/lib/bankrotData";
import { motion, type Variants, useScroll, useSpring } from "framer-motion";
import { Activity, AlertTriangle, ArrowLeft, Award, Building2, CalendarDays, ChevronUp, ClipboardCheck, Database, Download, ExternalLink, FileText, Globe, Loader2, Mail, Moon, Phone, Printer, RefreshCw, Share2, ShieldCheck, Sparkles, Store, Sun, Users, Zap } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import {
  getCompanyProfile,
  CompanyProfile,
  getGrpTaxpayerData,
  GrpTaxpayerData,
  getCompanyTaxDebt,
  CompanyTaxDebtResponse,
  getCompanyRelated,
  CompanyRelatedResponse,
  getCompanyRisk,
  CompanyRisk,
  getCompanyBankruptcy,
  CompanyBankrotResponse,
  downloadCompanyReport,
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

const cardReveal: Variants = {
  hidden: { opacity: 0, y: 18 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.4, ease: [0.16, 1, 0.3, 1] as const } },
};

// Wrapper for staggered card sections
const SectionCard = ({ children, className = "" }: { children: React.ReactNode; className?: string }) => (
  <motion.div variants={cardReveal} className={className}>
    {children}
  </motion.div>
);

type TradeRegistryRecord = NonNullable<CompanyProfile["trade_registry_records"]>[number];
type PulseTone = "emerald" | "amber" | "red" | "sky" | "violet";

// Skeleton block helper
const Skeleton = ({ className = "" }: { className?: string }) => (
  <div className={`animate-skeleton ${className}`} />
);

const RiskCategoryRadar = ({
  categories,
  color,
}: {
  categories: NonNullable<CompanyRisk["categories"]>;
  color: string;
}) => {
  const categoryDefaults = [
    { code: "legal", title: "Право", cap: 50 },
    { code: "fiscal", title: "Налоги", cap: 20 },
    { code: "compliance", title: "Реестры", cap: 20 },
    { code: "behavioral", title: "Поведение", cap: 10 },
  ];
  const radarCategories = categoryDefaults.map((fallback) => {
    const category = categories.find((item) => item.code === fallback.code);
    return category ?? { ...fallback, score: 0, raw_score: 0, level: "low" as const, factor_count: 0 };
  });
  const center = 90;
  const radius = 62;
  const point = (index: number, ratio: number) => {
    const angle = -Math.PI / 2 + (index * Math.PI * 2) / radarCategories.length;
    return `${center + Math.cos(angle) * radius * ratio},${center + Math.sin(angle) * radius * ratio}`;
  };
  const polygon = radarCategories
    .map((category, index) => point(index, Math.min(1, category.score / category.cap)))
    .join(" ");

  return (
    <div className="rounded-2xl border border-border/60 bg-background/50 p-4">
      <div className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
        Профиль по категориям
      </div>
      <svg viewBox="0 0 180 180" className="mx-auto mt-2 h-44 w-44" role="img" aria-label="Радар категорий риска">
        {[0.25, 0.5, 0.75, 1].map((ratio) => (
          <polygon
            key={ratio}
            points={radarCategories.map((_, index) => point(index, ratio)).join(" ")}
            fill="none"
            stroke="currentColor"
            strokeOpacity={ratio === 1 ? 0.22 : 0.1}
            strokeWidth="1"
          />
        ))}
        {radarCategories.map((category, index) => (
          <line
            key={category.code}
            x1={center}
            y1={center}
            x2={point(index, 1).split(",")[0]}
            y2={point(index, 1).split(",")[1]}
            stroke="currentColor"
            strokeOpacity="0.14"
          />
        ))}
        <polygon points={polygon} fill={color} fillOpacity="0.22" stroke={color} strokeWidth="2.5" />
        {radarCategories.map((category, index) => {
          const [coordinateX, coordinateY] = point(index, Math.min(1, category.score / category.cap)).split(",");
          return <circle key={category.code} cx={coordinateX} cy={coordinateY} r="3.5" fill={color} />;
        })}
      </svg>
      <div className="grid grid-cols-2 gap-2">
        {radarCategories.map((category) => (
          <div key={category.code} className="rounded-lg border border-border/50 bg-card/55 px-3 py-2">
            <div className="text-[11px] text-muted-foreground">{category.title}</div>
            <div className="mt-0.5 text-sm font-semibold text-foreground">
              {category.score}<span className="text-xs font-normal text-muted-foreground">/{category.cap}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

const CompanySkeleton = () => (
  <div className="space-y-6">
    <div className="relative overflow-hidden rounded-2xl border border-primary/10 bg-card/60 p-5 sm:p-6">
      <Skeleton className="h-5 w-32 mb-4" />
      <Skeleton className="h-8 w-48 mb-2" />
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-5">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="rounded-xl border border-border/50 bg-background/60 p-3">
            <Skeleton className="h-4 w-4 mb-2" />
            <Skeleton className="h-3 w-12 mb-1" />
            <Skeleton className="h-5 w-16" />
          </div>
        ))}
      </div>
    </div>
    <div className="rounded-2xl border border-border/50 bg-card/60 p-5 sm:p-6 space-y-3">
      <Skeleton className="h-6 w-40 mb-4" />
      {[...Array(4)].map((_, i) => (
        <div key={i} className="rounded-lg p-3 border border-border/30">
          <Skeleton className="h-3 w-20 mb-2" />
          <Skeleton className="h-5 w-full max-w-sm" />
        </div>
      ))}
    </div>
  </div>
);

const Company = () => {
  const { unp } = useParams();
  const [profile, setProfile] = useState<CompanyProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [grpData, setGrpData] = useState<GrpTaxpayerData | null>(null);
  const [grpLoading, setGrpLoading] = useState(false);
  const [taxDebtData, setTaxDebtData] = useState<CompanyTaxDebtResponse | null>(null);
  const [taxDebtLoading, setTaxDebtLoading] = useState(false);
  const [taxDebtError, setTaxDebtError] = useState<string | null>(null);
  const [relatedData, setRelatedData] = useState<CompanyRelatedResponse | null>(null);
  const [risk, setRisk] = useState<CompanyRisk | null>(null);
  const [riskLoading, setRiskLoading] = useState(false);
  const [riskError, setRiskError] = useState<string | null>(null);
  const [bankruptcyData, setBankruptcyData] = useState<CompanyBankrotResponse | null>(null);
  const [bankruptcyLoading, setBankruptcyLoading] = useState(false);
  const [bankruptcyError, setBankruptcyError] = useState<string | null>(null);
  const [showBankruptcyDetails, setShowBankruptcyDetails] = useState(false);
  const [isDark, setIsDark] = useState(false);
  const [showScrollTop, setShowScrollTop] = useState(false);
  const [expandedBeltppProducts, setExpandedBeltppProducts] = useState<Set<string>>(new Set());
  const [reportDownloading, setReportDownloading] = useState(false);
  const profileRequestRef = useRef(0);
  const grpRequestRef = useRef(0);
  const taxDebtRequestRef = useRef(0);
  const relatedRequestRef = useRef(0);
  const riskRequestRef = useRef(0);
  const bankruptcyRequestRef = useRef(0);
  const { toast } = useToast();

  const { scrollYProgress } = useScroll();
  const scaleX = useSpring(scrollYProgress, { stiffness: 200, damping: 30 });

  const handleDownloadReport = async () => {
    if (!unp || reportDownloading) return;
    setReportDownloading(true);
    try {
      const { blob, filename } = await downloadCompanyReport(unp);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      toast({ title: "Полное досье сформировано" });
    } catch (downloadError) {
      toast({
        title: "Не удалось скачать отчёт",
        description: downloadError instanceof Error ? downloadError.message : undefined,
        variant: "destructive",
      });
    } finally {
      setReportDownloading(false);
    }
  };

  const handleShareCompany = async () => {
    if (!profile) return;

    const title = profile.current_short_name_ru || profile.current_name_ru || `УНП ${profile.unp || unp}`;
    const text = `${title}: карточка компании в EGR`;
    const url = window.location.href;

    try {
      if (navigator.share) {
        await navigator.share({ title, text, url });
      } else {
        await navigator.clipboard.writeText(url);
        toast({ title: "Ссылка скопирована" });
      }
    } catch (shareError) {
      if (shareError instanceof DOMException && shareError.name === "AbortError") return;
      toast({
        title: "Не удалось поделиться ссылкой",
        description: shareError instanceof Error ? shareError.message : undefined,
        variant: "destructive",
      });
    }
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
    bankruptcyRequestRef.current += 1;
    setBankruptcyData(null);
    setBankruptcyError(null);
    setBankruptcyLoading(false);
    setShowBankruptcyDetails(false);
  }, [unp]);

  useEffect(() => {
    const load = async () => {
      const requestId = ++profileRequestRef.current;
      if (!unp) {
        setError("УНП не указан");
        setLoading(false);
        return;
      }
      setLoading(true);
      setError(null);
      setProfile(null);
      try {
        const data = await getCompanyProfile(unp);
        if (requestId === profileRequestRef.current) setProfile(data);
      } catch (err) {
        if (requestId === profileRequestRef.current) {
          setError(err instanceof Error ? err.message : "Ошибка загрузки профиля");
          setProfile(null);
        }
      } finally {
        if (requestId === profileRequestRef.current) setLoading(false);
      }
    };
    load();
  }, [unp]);

  useEffect(() => {
    const loadCachedGrp = async () => {
      const requestId = ++grpRequestRef.current;
      if (!unp) {
        setGrpData(null);
        setGrpLoading(false);
        return;
      }

      setGrpLoading(true);
      setGrpData(null);
      try {
        const data = await getGrpTaxpayerData(unp);
        if (requestId === grpRequestRef.current) setGrpData(data);
      } catch {
        if (requestId === grpRequestRef.current) setGrpData(null);
      } finally {
        if (requestId === grpRequestRef.current) setGrpLoading(false);
      }
    };

    loadCachedGrp();
  }, [unp]);

  useEffect(() => {
    const loadTaxDebt = async () => {
      if (!unp) return;
      const requestId = ++taxDebtRequestRef.current;
      setTaxDebtLoading(true);
      setTaxDebtError(null);
      setTaxDebtData(null);
      try {
        const data = await getCompanyTaxDebt(unp);
        if (requestId === taxDebtRequestRef.current) setTaxDebtData(data);
      } catch (err) {
        if (requestId === taxDebtRequestRef.current) {
          setTaxDebtError(
            err instanceof Error ? err.message : "Ошибка загрузки данных по налоговой задолженности"
          );
          setTaxDebtData(null);
        }
      } finally {
        if (requestId === taxDebtRequestRef.current) setTaxDebtLoading(false);
      }
    };

    loadTaxDebt();
  }, [unp]);

  useEffect(() => {
    // Второстепенный блок: молча ничего не показываем при ошибке/отсутствии совпадений.
    const loadRelated = async () => {
      if (!unp) return;
      const requestId = ++relatedRequestRef.current;
      setRelatedData(null);
      try {
        const data = await getCompanyRelated(unp);
        if (requestId === relatedRequestRef.current) setRelatedData(data);
      } catch {
        if (requestId === relatedRequestRef.current) setRelatedData(null);
      }
    };
    loadRelated();
  }, [unp]);

  const loadRisk = async () => {
    if (!unp) return;
    const requestId = ++riskRequestRef.current;
    setRiskLoading(true);
    setRiskError(null);
    setRisk(null);
    try {
      const data = await getCompanyRisk(unp);
      if (requestId === riskRequestRef.current) setRisk(data);
    } catch (riskLoadError) {
      if (requestId === riskRequestRef.current) {
        setRisk(null);
        setRiskError(riskLoadError instanceof Error ? riskLoadError.message : "Не удалось рассчитать риск");
      }
    } finally {
      if (requestId === riskRequestRef.current) setRiskLoading(false);
    }
  };

  useEffect(() => {
    loadRisk();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unp]);

  useEffect(() => {
    const onScroll = () => setShowScrollTop(window.scrollY > 400);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

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

  const toggleBankruptcyDetails = async () => {
    if (showBankruptcyDetails) {
      setShowBankruptcyDetails(false);
      return;
    }
    setShowBankruptcyDetails(true);
    if (!unp || bankruptcyData || bankruptcyLoading) return;

    const requestId = ++bankruptcyRequestRef.current;
    setBankruptcyLoading(true);
    setBankruptcyError(null);
    try {
      const data = await getCompanyBankruptcy(unp);
      if (requestId === bankruptcyRequestRef.current) setBankruptcyData(data);
    } catch (err) {
      if (requestId === bankruptcyRequestRef.current) {
        setBankruptcyError(
          err instanceof Error ? err.message : "Ошибка загрузки данных о банкротстве"
        );
      }
    } finally {
      if (requestId === bankruptcyRequestRef.current) setBankruptcyLoading(false);
    }
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

  const toggleBeltppProducts = (key: string) => {
    setExpandedBeltppProducts((current) => {
      const next = new Set(current);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const formatInspectionRegion = (value?: string) => {
    const normalized = (value || "").trim().toLowerCase();
    const labels: Record<string, string> = {
      "брестская область": "Брестская область",
      "витебская область": "Витебская область",
      "гомельская область": "Гомельская область",
      "гродненская область": "Гродненская область",
      "минская область": "Минская область",
      "могилевская область": "Могилевская область",
      "могилёвская область": "Могилевская область",
      "минск": "г. Минск",
      "г. минск": "г. Минск",
    };
    return labels[normalized] || value || "—";
  };

  const formatInspectionPeriod = (value?: string, year?: number, half?: number) => {
    if (year && half === 1) return `первое полугодие ${year}`;
    if (year && half === 2) return `второе полугодие ${year}`;
    if (year) return String(year);

    const match = (value || "").match(/^(\d{4})-H([12])$/i);
    if (match) {
      return `${match[2] === "1" ? "первое" : "второе"} полугодие ${match[1]}`;
    }
    return value || "—";
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

  const businessPulse = profile ? (() => {
    const registeredAt = profile.registration_date ? new Date(profile.registration_date).getTime() : NaN;
    const ageYears = Number.isFinite(registeredAt)
      ? Math.max(0, Math.floor((Date.now() - registeredAt) / (365.25 * 24 * 60 * 60 * 1000)))
      : null;
    const taxDebtCount = taxDebtData?.count ?? 0;
    const currentTaxDebtCount = taxDebtData?.current_count ?? 0;
    const hasCurrentTaxDebt = taxDebtData?.has_current_debt ?? currentTaxDebtCount > 0;
    const activeLicenses = profile.license_records?.filter((item) => item.activity_is_active).length ?? 0;
    const inspectionsCount = profile.inspection_plan_records?.length ?? 0;
    const relatedCount = (relatedData?.by_address.length ?? 0) + (relatedData?.by_contact.length ?? 0);
    const riskScore = risk?.score ?? null;
    const confidence = risk?.coverage?.score ?? null;
    const healthLabel = risk?.decision_label
      ?? (riskLoading ? "Скоринг рассчитывается" : riskError ? "Скоринг недоступен" : "Оценка не получена");
    const healthTone: PulseTone = risk?.decision === "stop" || risk?.decision === "manual_review"
      ? "red"
      : risk?.decision === "review" || risk?.level === "medium"
        ? "amber"
        : risk?.decision === "clear" || risk?.level === "low"
          ? "emerald"
          : "sky";
    const summary = risk?.summary
      ?? (riskLoading
        ? "Проверяем ключевые государственные источники и рассчитываем профиль риска."
        : "Риск-профиль пока недоступен; фактические данные карточки показаны без подмены балла.");
    const timeline = [
      profile.registration_date && { label: "Регистрация", value: formatDate(profile.registration_date), icon: CalendarDays },
      profile.liquidation_date && { label: "Ликвидация", value: formatDate(profile.liquidation_date), icon: AlertTriangle },
      taxDebtData?.latest_slice_date && { label: "Последний срез долгов", value: formatDate(taxDebtData.latest_slice_date), icon: AlertTriangle },
    ].filter(Boolean).slice(0, 4) as { label: string; value: string; icon: typeof CalendarDays }[];
    const signals: { label: string; value: string; tone: PulseTone }[] = [
      {
        label: "Покрытие источников",
        value: confidence === null ? "—" : `${confidence}%`,
        tone: confidence !== null && confidence >= 80 ? "emerald" : "sky",
      },
      { label: "Возраст", value: ageYears === null ? "нет даты" : `${ageYears} лет`, tone: "violet" },
      {
        label: "Долги МНС",
        value: hasCurrentTaxDebt ? `${currentTaxDebtCount} акт.` : taxDebtCount > 0 ? `${taxDebtCount} ист.` : "0",
        tone: hasCurrentTaxDebt ? "red" : taxDebtCount > 0 ? "amber" : "emerald",
      },
      { label: "Активные лицензии", value: String(activeLicenses), tone: activeLicenses > 0 ? "emerald" : "sky" },
      { label: "Плановые проверки", value: String(inspectionsCount), tone: "sky" },
      { label: "Связи", value: String(relatedCount), tone: relatedCount > 0 ? "violet" : "sky" },
    ];

    return { confidence, healthLabel, healthTone, riskScore, signals, summary, timeline };
  })() : null;

  return (
    <div className="min-h-screen bg-background px-4 pb-12 pt-28 relative overflow-hidden" style={{
      background: 'linear-gradient(135deg, hsl(var(--background)) 0%, hsl(var(--background)) 70%, hsl(var(--secondary) / 0.2) 100%)'
    }}>

      {/* Scroll progress bar */}
      <motion.div
        className="fixed top-0 left-0 right-0 h-[2px] z-[60] origin-left"
        style={{
          scaleX,
          background: 'linear-gradient(90deg, hsl(var(--primary)), hsl(var(--accent)))',
        }}
      />

      {/* Scroll to top button */}
      <motion.button
        initial={false}
        animate={{ opacity: showScrollTop ? 1 : 0, y: showScrollTop ? 0 : 12 }}
        transition={{ duration: 0.2 }}
        onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
        className="fixed bottom-6 right-6 z-50 w-11 h-11 rounded-full glass shadow-card hover:shadow-glow transition-all duration-300 flex items-center justify-center pointer-events-auto"
        style={{ pointerEvents: showScrollTop ? "auto" : "none" }}
        aria-label="Наверх"
      >
        <ChevronUp className="w-5 h-5" />
      </motion.button>

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
        <div className="ambient-orb-primary absolute left-10 top-20 hidden h-72 w-72 dark:opacity-25 sm:block" />
        <div className="ambient-orb-accent absolute bottom-20 right-10 hidden h-96 w-96 dark:opacity-30 sm:block" />
        <div className="ambient-orb-primary absolute left-1/2 top-1/2 hidden h-[500px] w-[500px] -translate-x-1/2 -translate-y-1/2 dark:opacity-15 lg:block" />
        {/* Mobile decorative elements */}
        <div className="ambient-orb-primary absolute right-10 top-10 h-32 w-32 dark:opacity-20 sm:hidden" />
        <div className="ambient-orb-accent absolute bottom-10 left-10 h-24 w-24 dark:opacity-25 sm:hidden" />
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

        <div className="space-y-3">
          <h1 className="max-w-6xl text-2xl font-bold leading-tight text-foreground break-words sm:text-3xl md:text-4xl">
            {profile?.current_name_ru || profile?.current_short_name_ru || "Профиль компании"}
          </h1>
          {unp && (
            <span className="inline-flex rounded-full glass px-3 py-1 text-sm font-medium text-primary">
              УНП {unp}
            </span>
          )}
        </div>

        {unp && (
          <div className="space-y-2 rounded-2xl border border-border/70 bg-card/95 p-3 shadow-soft">
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <Button
                type="button"
                variant="default"
                onClick={handleDownloadReport}
                disabled={reportDownloading || !profile}
                className="w-full min-w-0"
              >
                {reportDownloading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
                Скачать досье
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={handleShareCompany}
                disabled={!profile}
                className="w-full min-w-0 glass hover:bg-primary/10 dark:hover:bg-primary/20"
              >
                <Share2 className="h-4 w-4" />
                Поделиться
              </Button>
            </div>
            <div className="border-t border-border/60 pt-2">
              <Button asChild size="sm" variant="outline" className="w-full min-w-0 glass hover:bg-primary/10 dark:hover:bg-primary/20">
                <Link to={`/company/${unp}/relations`}>
                  <Users className="h-4 w-4" />
                  Карта связей
                </Link>
              </Button>
            </div>
          </div>
        )}

        {loading && <CompanySkeleton />}
        {profile && (
          <motion.div
            variants={cardReveal}
            initial="hidden"
            animate="visible"
            transition={{ duration: 0.45, delay: 0.08 }}
            className="relative overflow-hidden rounded-2xl border border-primary/20 bg-card/95 shadow-card"
          >
            <div className="absolute inset-0 registry-grid opacity-30" />
            <motion.div
              className="absolute inset-y-0 -left-32 w-28 bg-gradient-to-r from-transparent via-primary/10 to-transparent"
              initial={{ x: "0%" }}
              animate={{ x: ["0%", "950%"] }}
              transition={{ duration: 2.4, delay: 0.7, ease: "easeInOut" }}
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
              hidden: {},
              visible: { transition: { staggerChildren: 0.06, delayChildren: 0.05 } },
            }}
            initial="hidden"
            animate="visible"
            className="space-y-6"
          >
            {businessPulse && (() => {
              const toneClasses: Record<PulseTone, string> = {
                emerald: "border-emerald-500/25 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
                amber: "border-amber-500/25 bg-amber-500/10 text-amber-700 dark:text-amber-300",
                red: "border-red-500/25 bg-red-500/10 text-red-700 dark:text-red-300",
                sky: "border-sky-500/25 bg-sky-500/10 text-sky-700 dark:text-sky-300",
                violet: "border-violet-500/25 bg-violet-500/10 text-violet-700 dark:text-violet-300",
              };

              return (
                <SectionCard>
                  <Card className="relative overflow-hidden border-primary/25 bg-card/95 shadow-card transition-shadow duration-300 hover:shadow-glow">
                    <div className="absolute inset-0 registry-grid opacity-25" />
                    <div className="ambient-orb-primary absolute -right-24 -top-24 h-56 w-56" />
                    <CardHeader className="relative rounded-t-lg" style={{
                      background: "linear-gradient(120deg, hsl(var(--primary) / 0.12), hsl(var(--accent) / 0.10), transparent)",
                    }}>
                      <CardTitle className="text-foreground flex flex-wrap items-center gap-2 text-lg sm:text-xl">
                        <Sparkles className="w-5 h-5 text-primary" />
                        Business Pulse
                        <span className={`rounded-full border px-2.5 py-1 text-xs font-medium ${toneClasses[businessPulse.healthTone]}`}>
                          {businessPulse.healthLabel}
                        </span>
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="relative space-y-5 p-4 sm:p-6">
                      <div className="grid gap-3 md:grid-cols-[1.05fr_1.6fr]">
                        <div className={`rounded-2xl border p-4 ${toneClasses[businessPulse.healthTone]}`}>
                          <div className="flex items-center justify-between gap-3">
                            <div>
                              <div className="text-xs uppercase tracking-[0.2em] opacity-80">радар риска</div>
                              <div className="mt-2 text-4xl font-bold leading-none">{businessPulse.riskScore ?? "—"}</div>
                              <div className="mt-1 text-xs opacity-80">
                                {businessPulse.riskScore === null ? "ожидаем расчёт" : "из 100 по открытым сигналам"}
                              </div>
                            </div>
                            <div className="relative h-20 w-20">
                              <div className="absolute inset-0 rounded-full border border-current/20" />
                              <div className="absolute inset-3 rounded-full border border-current/30" />
                              <div className="absolute left-1/2 top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-current shadow-[0_0_24px_currentColor]" />
                              <Zap className="absolute right-2 top-2 h-4 w-4" />
                            </div>
                          </div>
                        </div>

                        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                          {businessPulse.signals.map((signal) => (
                            <div key={signal.label} className={`rounded-xl border p-3 ${toneClasses[signal.tone]}`}>
                              <div className="text-[11px] uppercase tracking-wide opacity-80">{signal.label}</div>
                              <div className="mt-1 text-lg font-semibold text-foreground">{signal.value}</div>
                            </div>
                          ))}
                        </div>
                      </div>

                      <div className="grid gap-3 md:grid-cols-2">
                        <div className="rounded-xl border border-border/60 bg-background/55 p-4">
                          <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
                            <Activity className="h-4 w-4 text-primary" />
                            Быстрый вывод
                          </div>
                          <p className="text-sm text-muted-foreground">
                            {businessPulse.summary}
                            {businessPulse.confidence !== null && (
                              <> Покрытие ключевых источников: {businessPulse.confidence}%.</>
                            )}
                          </p>
                        </div>

                        <div className="rounded-xl border border-border/60 bg-background/55 p-4">
                          <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
                            <ShieldCheck className="h-4 w-4 text-primary" />
                            Таймлайн
                          </div>
                          <div className="space-y-2">
                            {businessPulse.timeline.length > 0 ? businessPulse.timeline.map((event) => (
                              <div key={`${event.label}-${event.value}`} className="flex items-center gap-2 text-sm">
                                <event.icon className="h-3.5 w-3.5 text-primary" />
                                <span className="text-muted-foreground">{event.label}</span>
                                <span className="ml-auto text-right font-medium text-foreground">{event.value}</span>
                              </div>
                            )) : (
                              <div className="text-sm text-muted-foreground">Событий для таймлайна пока недостаточно.</div>
                            )}
                          </div>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </SectionCard>
              );
            })()}

            {riskLoading && (
              <SectionCard>
                <Card className="glass border-primary/25 shadow-card">
                  <CardContent className="flex items-center gap-3 p-5 text-sm text-muted-foreground">
                    <Loader2 className="h-5 w-5 animate-spin text-primary" />
                    Проверяем источники и рассчитываем объяснимый риск-профиль…
                  </CardContent>
                </Card>
              </SectionCard>
            )}

            {riskError && !riskLoading && (
              <SectionCard>
                <Card className="glass border-amber-500/30 shadow-card">
                  <CardContent className="flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <div className="font-semibold text-foreground">Риск-профиль временно недоступен</div>
                      <div className="mt-1 text-sm text-muted-foreground">{riskError}</div>
                    </div>
                    <Button variant="outline" onClick={loadRisk} className="gap-2">
                      <RefreshCw className="h-4 w-4" />
                      Повторить
                    </Button>
                  </CardContent>
                </Card>
              </SectionCard>
            )}

            {risk && (() => {
              const decision = risk.decision ?? (risk.level === "high" ? "manual_review" : risk.level === "medium" ? "review" : "clear");
              const decisionMeta = {
                stop: { color: "#dc2626", bg: "rgba(220,38,38,0.10)", label: "Стоп-фактор" },
                manual_review: { color: "#dc2626", bg: "rgba(220,38,38,0.10)", label: "Ручная проверка" },
                review: { color: "#d97706", bg: "rgba(217,119,6,0.10)", label: "Требует внимания" },
                incomplete: { color: "#0284c7", bg: "rgba(2,132,199,0.10)", label: "Неполные данные" },
                clear: { color: "#16a34a", bg: "rgba(22,163,74,0.10)", label: "Стоп-сигналов нет" },
              }[decision];
              const severityLabels: Record<string, string> = {
                critical: "критично",
                high: "высокий",
                medium: "средний",
                low: "низкий",
              };
              const coverage = risk.coverage;
              return (
                <SectionCard>
                  <Card className="glass overflow-hidden shadow-card transition-all duration-300 hover:shadow-glow" style={{ borderColor: decisionMeta.color + "55" }}>
                    <CardHeader className="rounded-t-lg" style={{ background: decisionMeta.bg }}>
                      <CardTitle className="text-foreground flex items-center gap-2 text-lg sm:text-xl">
                        <ShieldCheck className="h-5 w-5" style={{ color: decisionMeta.color }} />
                        Радар риска
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="p-4 sm:p-6 space-y-5">
                      <div className="grid gap-4 lg:grid-cols-[0.8fr_1.15fr_1fr]">
                        <div className="flex min-h-64 flex-col items-center justify-center rounded-2xl border border-border/60 bg-background/50 p-4 text-center">
                          <div
                            className="grid h-36 w-36 place-items-center rounded-full p-2"
                            style={{ background: `conic-gradient(${decisionMeta.color} ${risk.score * 3.6}deg, hsl(var(--muted)) 0deg)` }}
                          >
                            <div className="grid h-full w-full place-items-center rounded-full bg-card shadow-inner">
                              <div>
                                <div className="text-4xl font-bold leading-none" style={{ color: decisionMeta.color }}>{risk.score}</div>
                                <div className="mt-1 text-xs text-muted-foreground">из 100</div>
                              </div>
                            </div>
                          </div>
                          <div className="mt-4 text-lg font-bold" style={{ color: decisionMeta.color }}>{decisionMeta.label}</div>
                        </div>

                        <RiskCategoryRadar categories={risk.categories ?? []} color={decisionMeta.color} />

                        <div className="flex min-h-64 flex-col rounded-2xl border border-border/60 bg-background/50 p-4">
                          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">Вывод</div>
                          <div className="mt-3 text-xl font-bold text-foreground">{risk.decision_label ?? decisionMeta.label}</div>
                          <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                            {risk.summary ?? "Оценка рассчитана по доступным государственным источникам."}
                          </p>
                          <div className="mt-auto pt-5">
                            <div className="flex items-center justify-between text-xs text-muted-foreground">
                              <span>Покрытие источников</span>
                              <span className="font-semibold text-foreground">{coverage?.score ?? "—"}%</span>
                            </div>
                            <div className="mt-2 h-2 overflow-hidden rounded-full bg-muted">
                              <div className="h-full rounded-full transition-[width] duration-500" style={{ width: `${coverage?.score ?? 0}%`, background: decisionMeta.color }} />
                            </div>
                            <div className="mt-2 text-xs text-muted-foreground">
                              {coverage ? `${coverage.checked_sources} из ${coverage.total_sources} ключевых источников` : "Нет данных о покрытии"}
                            </div>
                            {risk.scope?.note && (
                              <div className="mt-3 border-t border-border/50 pt-3 text-xs leading-relaxed text-muted-foreground">
                                {risk.scope.note}
                              </div>
                            )}
                          </div>
                        </div>
                      </div>

                      {risk.factors.length > 0 ? (
                        <div className="space-y-2">
                          <div className="flex items-center justify-between gap-3 text-sm font-semibold text-foreground">
                            <span>Почему такой балл</span>
                          </div>
                          {risk.factors.map((factor) => (
                            <div key={factor.code} className="glass rounded-xl p-3 flex items-start gap-3">
                              <span
                                className="flex-shrink-0 text-xs font-bold px-2 py-1 rounded-md"
                                style={{ color: decisionMeta.color, background: decisionMeta.bg }}
                              >
                                +{factor.weight}
                              </span>
                              <div className="min-w-0">
                                <div className="flex flex-wrap items-center gap-2">
                                  <div className="text-sm font-medium text-foreground">{factor.title}</div>
                                  {factor.severity && (
                                    <span className="rounded-full border border-border/60 px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                                      {severityLabels[factor.severity] ?? factor.severity}
                                    </span>
                                  )}
                                </div>
                                <div className="mt-0.5 text-xs text-muted-foreground">{factor.detail}</div>
                                {(factor.source || factor.observed_at) && (
                                  <div className="mt-1.5 text-[11px] text-muted-foreground/80">
                                    {[factor.source, factor.observed_at ? `данные на ${formatDate(factor.observed_at)}` : null].filter(Boolean).join(" · ")}
                                  </div>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="text-sm text-muted-foreground">Значимых факторов риска не обнаружено.</div>
                      )}

                      {risk.trust_signals.length > 0 && (
                        <div className="space-y-2">
                          <div className="text-sm font-semibold text-foreground">Сигналы доверия</div>
                          <div className="flex flex-wrap gap-2">
                            {risk.trust_signals.map((signal) => (
                              <span
                                key={signal.code}
                                className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-full"
                                style={{ color: "#16a34a", background: "rgba(22,163,74,0.10)" }}
                                title={`${signal.detail}${signal.source ? ` · ${signal.source}` : ""}`}
                              >
                                <Award className="w-3 h-3" />
                                {signal.title}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {coverage && (
                        <div className="rounded-xl border border-border/60 bg-background/45 p-4">
                          <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
                            <Database className="h-4 w-4 text-primary" />
                            Проверенные источники
                          </div>
                          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                            {coverage.sources.map((source) => (
                              <div key={source.code} className="flex items-center gap-2 rounded-lg border border-border/50 bg-card/50 px-3 py-2">
                                <span className={`h-2 w-2 rounded-full ${source.status === "fresh" || (source.available && !source.status) ? "bg-emerald-500" : source.status === "stale" ? "bg-amber-500" : "bg-slate-400"}`} />
                                <div className="min-w-0">
                                  <div className="truncate text-xs font-medium text-foreground">{source.title}</div>
                                  <div className="text-[11px] text-muted-foreground">
                                    {source.checked_at
                                      ? `${source.status === "stale" ? "устарел · " : ""}${formatDate(source.checked_at)}`
                                      : "нет подтверждённого среза"}
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                </SectionCard>
              );
            })()}

            <SectionCard>
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
                    const dateKeys = new Set(["registration_date", "liquidation_date"]);
                    const raw = typeof rawValue === "string" ? rawValue : String(rawValue);
                    const value = dateKeys.has(key) ? formatDate(raw) : raw;
                    return (
                      <div key={key} className="glass p-3 sm:p-4 rounded-lg hover:bg-primary/5 dark:hover:bg-primary/10 transition-all duration-300">
                        <span className="text-xs sm:text-sm text-muted-foreground font-medium block mb-1">{label}</span>
                        <span className="text-foreground font-semibold text-sm sm:text-base leading-relaxed">{value}</span>
                      </div>
                    );
                  })}
                </CardContent>
              </Card>
            </SectionCard>

          {profile.leadership_observations && profile.leadership_observations.length > 0 && (
            <SectionCard>
              <Card className="glass overflow-hidden border-amber-500/25 shadow-card">
                <CardHeader className="border-b border-border/60 bg-gradient-to-r from-amber-500/10 via-primary/5 to-transparent">
                  <CardTitle className="flex items-center gap-2 text-lg sm:text-xl">
                    <Users className="h-5 w-5 text-amber-600 dark:text-amber-400" />
                    Руководители в открытых публикациях
                  </CardTitle>
                  <p className="text-sm leading-relaxed text-muted-foreground">
                    Датированные сведения Комитета по труду Минска. Источник не содержит УНП,
                    поэтому привязка выполнена только по однозначному совпадению названия и не
                    подтверждает, что человек занимает должность сейчас.
                  </p>
                </CardHeader>
                <CardContent className="space-y-3 p-4 sm:p-6">
                  {profile.leadership_observations.map((item) => (
                    <div
                      key={`${item.source_url}-${item.person_name}-${item.position}`}
                      className="rounded-xl border border-border/60 bg-background/50 p-4"
                    >
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                        <div>
                          <div className="font-semibold text-foreground">{item.person_name}</div>
                          <div className="mt-1 text-sm text-muted-foreground">{item.position}</div>
                          <div className="mt-1 text-xs text-muted-foreground/80">
                            В публикации: {item.organization_name}
                            {item.event_date ? ` · список на ${formatDate(item.event_date)}` : ""}
                          </div>
                        </div>
                        <Button asChild size="sm" variant="outline" className="shrink-0">
                          <a href={item.source_url} target="_blank" rel="noopener noreferrer">
                            Источник
                            <ExternalLink className="ml-1.5 h-3.5 w-3.5" />
                          </a>
                        </Button>
                      </div>
                    </div>
                  ))}
                </CardContent>
              </Card>
            </SectionCard>
          )}

          {profile.gias_bank_accounts && profile.gias_bank_accounts.length > 0 && (
            <SectionCard>
              <GiasBankAccountsSection
                accounts={profile.gias_bank_accounts}
                companyUnp={profile.unp}
              />
            </SectionCard>
          )}

          {/* История названий */}
          {profile.names && profile.names.length > 0 && (
            <SectionCard>
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
                {profile.names.map((name, idx) => {
                  return (
                    <div
                      key={idx}
                      className="glass p-3 sm:p-4 rounded-lg hover:bg-accent/5 dark:hover:bg-accent/10 transition-all duration-300 border-l-4 border-accent/30 relative"
                    >
                      <div className="absolute top-2 sm:top-3 right-2 sm:right-3 opacity-50">
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
                      <div className="text-sm sm:text-base text-muted-foreground px-2 py-1 inline-block mt-2 rounded-md bg-muted/40">
                        <div className="flex items-center gap-2">
                          <div className={`w-2 h-2 rounded-full ${!name.valid_to ? 'bg-green-500 animate-pulse' : 'bg-primary/60 dark:bg-primary/80'}`}></div>
                          <span className="font-medium">
                            {name.valid_from ? `С ${formatDate(name.valid_from)}` : "С даты не указано"}
                            {name.valid_to ? ` по ${formatDate(name.valid_to)}` : " по настоящее время"}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                  );
                })}
              </CardContent>
            </Card>
            </SectionCard>
          )}

          {/* Карта местоположения: по сохранённым координатам (OSM), иначе геокод на лету */}
          {(() => {
            const currentAddress =
              profile.place_location_address ??
              profile.addresses?.find((a) => !a.valid_to)?.full_address ??
              profile.addresses?.[0]?.full_address;
            const hasCoords =
              typeof profile.latitude === "number" && typeof profile.longitude === "number";
            return currentAddress || hasCoords ? (
              <SectionCard>
                <CompanyMap
                  address={currentAddress}
                  unp={unp ?? String(profile.unp)}
                  lat={profile.latitude}
                  lon={profile.longitude}
                  name={profile.current_name_ru}
                />
              </SectionCard>
            ) : null;
          })()}

          {/* История адресов */}
          {profile.addresses && profile.addresses.length > 0 && (
            <SectionCard>
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
                {profile.addresses.map((addr, idx) => {
                  return (
                    <div
                      key={idx}
                      className="glass p-3 sm:p-4 rounded-lg hover:bg-secondary/5 dark:hover:bg-secondary/10 transition-all duration-300 border-l-4 border-secondary/30 relative"
                    >
                      <div className="absolute top-2 sm:top-3 right-2 sm:right-3 opacity-50">
                        <div className="w-1.5 h-1.5 sm:w-2 sm:h-2 rounded-full bg-secondary/50"></div>
                      </div>
                      <p className="text-foreground font-semibold text-sm sm:text-base mb-2 pr-4 sm:pr-6">{addr.full_address}</p>
                    {(addr.region || addr.district) && (
                      <p className="text-xs sm:text-sm text-muted-foreground bg-primary/10 dark:bg-primary/20 px-2 py-1 rounded-full inline-block mb-2">
                        {[addr.region, addr.district].filter(Boolean).join(", ")}
                      </p>
                    )}
                    <div className="text-sm sm:text-base text-muted-foreground px-2 py-1 inline-block mt-2 rounded-md bg-muted/40">
                      <div className="flex items-center gap-2">
                          <div className={`w-2 h-2 rounded-full ${!addr.valid_to ? 'bg-green-500 animate-pulse' : 'bg-accent/60 dark:bg-accent/80'}`}></div>
                        <span className="font-medium">
                          {addr.valid_from ? `С ${formatDate(addr.valid_from)}` : "С даты не указано"}
                          {addr.valid_to ? ` по ${formatDate(addr.valid_to)}` : " по настоящее время"}
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
            </SectionCard>
          )}

          {/* История ВЭД */}
          {profile.ved && profile.ved.length > 0 && (
            <SectionCard>
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
                {profile.ved.map((v, idx) => {
                  return (
                    <div
                      key={idx}
                      className="glass p-3 sm:p-4 rounded-lg hover:bg-primary/5 dark:hover:bg-primary/10 transition-all duration-300 border-l-4 border-primary/30 relative"
                    >
                      <div className="absolute top-2 sm:top-3 right-2 sm:right-3 opacity-50">
                        <div className="w-1.5 h-1.5 sm:w-2 sm:h-2 rounded-full bg-primary/50"></div>
                      </div>
                      <div className="flex flex-col sm:flex-row sm:gap-3 gap-2 items-start pr-4 sm:pr-6">
                      <span className="font-mono text-xs sm:text-sm glass px-2 py-1 rounded bg-primary/10 dark:bg-primary/20 text-primary font-semibold flex-shrink-0 w-fit">
                        {v.ved_code}
                      </span>
                      <span className="text-foreground font-medium flex-1 text-sm sm:text-base">{v.ved_name}</span>
                    </div>
                    <div className="text-sm sm:text-base text-muted-foreground px-2 py-1 inline-block mt-2 rounded-md bg-muted/40">
                      <div className="flex items-center gap-2">
                        <div className={`w-2 h-2 rounded-full ${!v.valid_to ? 'bg-green-500 animate-pulse' : 'bg-secondary/60 dark:bg-secondary/80'}`}></div>
                        <span className="font-medium">
                          {v.valid_from ? `С ${formatDate(v.valid_from)}` : "С даты не указано"}
                          {v.valid_to ? ` по ${formatDate(v.valid_to)}` : " по настоящее время"}
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
            </SectionCard>
          )}

          {/* Контактная информация */}
          {profile.contacts && profile.contacts.length > 0 && (
            <SectionCard>
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
            </SectionCard>
          )}

          {/* Данные налоговой (GRP) */}
          {(grpLoading || grpData) && (
          <SectionCard>
          <Card className="glass shadow-card hover:shadow-glow transition-all duration-300 border-primary/15">
            <CardHeader className="rounded-t-lg" style={{
              background: 'linear-gradient(90deg, hsl(var(--primary) / 0.08) 0%, hsl(var(--secondary) / 0.08) 100%)'
            }}>
              <CardTitle className="text-foreground flex items-center gap-2 text-lg sm:text-xl">
                <div className="w-2 h-2 rounded-full bg-primary animate-pulse"></div>
                Данные налоговой
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4 sm:p-6">
              {grpLoading && !grpData && (
                <p className="text-muted-foreground text-sm">Загрузка данных из налоговой...</p>
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
                </div>
              )}
            </CardContent>
          </Card>
          </SectionCard>
          )}

          {profile.pvt_resident && (
            <SectionCard>
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
                  {profile.pvt_resident.city && (
                    <div>
                      <span className="text-xs sm:text-sm text-muted-foreground font-medium block mb-1">Город</span>
                      <p className="text-foreground text-sm sm:text-base">{profile.pvt_resident.city}</p>
                    </div>
                  )}
                  {profile.pvt_resident.legal_address && (
                    <div>
                      <span className="text-xs sm:text-sm text-muted-foreground font-medium block mb-1">Юридический адрес</span>
                      <p className="text-foreground text-sm sm:text-base">{profile.pvt_resident.legal_address}</p>
                    </div>
                  )}
                  {profile.pvt_resident.phone && (
                    <div>
                      <span className="text-xs sm:text-sm text-muted-foreground font-medium block mb-1">Телефон</span>
                      <p className="text-foreground text-sm sm:text-base">{profile.pvt_resident.phone}</p>
                    </div>
                  )}
                  {profile.pvt_resident.website && (
                    <div>
                      <span className="text-xs sm:text-sm text-muted-foreground font-medium block mb-1">Сайт</span>
                      <a
                        href={profile.pvt_resident.website}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-primary hover:text-primary/80 font-semibold underline decoration-primary/30 hover:decoration-primary transition-all duration-300 text-sm break-all"
                      >
                        {profile.pvt_resident.website}
                      </a>
                    </div>
                  )}
                  {profile.pvt_resident.activity_directions && profile.pvt_resident.activity_directions.length > 0 && (
                    <div>
                      <span className="text-xs sm:text-sm text-muted-foreground font-medium block mb-1">Направления деятельности</span>
                      <div className="flex flex-wrap gap-2">
                        {profile.pvt_resident.activity_directions.map((direction, index) => (
                          <span key={`${direction}-${index}`} className="px-2 py-1 rounded-md bg-primary/10 text-primary text-xs font-medium">
                            {direction}
                          </span>
                        ))}
                      </div>
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
                </div>
              </CardContent>
            </Card>
            </SectionCard>
          )}

          {profile.eaeu_sez_resident_records && profile.eaeu_sez_resident_records.length > 0 && (
            <SectionCard>
            <Card className="glass shadow-card hover:shadow-glow transition-all duration-300 border-emerald-500/25">
              <CardHeader className="rounded-t-lg" style={{
                background: 'linear-gradient(90deg, hsl(150 70% 40% / 0.12) 0%, hsl(var(--primary) / 0.08) 100%)'
              }}>
                <CardTitle className="text-foreground flex items-center gap-2 text-lg sm:text-xl">
                  <Building2 className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
                  Резидент СЭЗ ЕАЭС
                  <span className="ml-auto text-sm font-normal text-muted-foreground">
                    Записей: {profile.eaeu_sez_resident_records.length}
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 sm:space-y-4 p-4 sm:p-6">
                {profile.eaeu_sez_resident_records.map((record, idx) => (
                  <div key={`${record.item_id}-${idx}`} className="glass p-3 sm:p-4 rounded-lg hover:bg-emerald-500/5 transition-all duration-300 space-y-3">
                    <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2">
                      <div>
                        <span className="text-xs sm:text-sm text-muted-foreground font-medium block mb-1">СЭЗ</span>
                        <p className="text-foreground font-semibold text-sm sm:text-base leading-relaxed">
                          {record.sez_name || "—"}
                        </p>
                      </div>
                      {record.certificate && (
                        <span className="font-mono text-xs glass px-2 py-1 rounded bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 font-semibold w-fit">
                          {record.certificate}
                        </span>
                      )}
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                      {record.short_name && (
                        <div>
                          <span className="text-muted-foreground block">Краткое наименование</span>
                          <span className="text-foreground font-medium">{record.short_name}</span>
                        </div>
                      )}
                      {record.firm_name && (
                        <div>
                          <span className="text-muted-foreground block">Фирменное наименование</span>
                          <span className="text-foreground font-medium">{record.firm_name}</span>
                        </div>
                      )}
                      {record.registration_agency && (
                        <div className="sm:col-span-2">
                          <span className="text-muted-foreground block">Орган регистрации</span>
                          <span className="text-foreground font-medium">{record.registration_agency}</span>
                        </div>
                      )}
                      {record.registry_entry_date && (
                        <div>
                          <span className="text-muted-foreground block">Дата записи</span>
                          <span className="text-foreground font-medium">{record.registry_entry_date}</span>
                        </div>
                      )}
                    </div>

                    {record.legal_address && (
                      <div className="text-sm">
                        <span className="text-muted-foreground block">Юридический адрес</span>
                        <span className="text-foreground font-medium">{record.legal_address}</span>
                      </div>
                    )}
                    {record.project_name && (
                      <div className="text-sm">
                        <span className="text-muted-foreground block">Проект</span>
                        <span className="text-foreground font-medium">{record.project_name}</span>
                      </div>
                    )}
                    {record.source_url && (
                      <a
                        href={record.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-2 text-primary hover:text-primary/80 font-semibold underline decoration-primary/30 hover:decoration-primary transition-all duration-300 text-sm"
                      >
                        <ExternalLink className="h-4 w-4" />
                        Запись в реестре ЕАЭС
                      </a>
                    )}
                  </div>
                ))}
              </CardContent>
            </Card>
            </SectionCard>
          )}

          {profile.license_records && profile.license_records.length > 0 && (
            <SectionCard>
            <Card className="glass shadow-card hover:shadow-glow transition-all duration-300 border-sky-500/25">
              <CardHeader className="rounded-t-lg" style={{
                background: 'linear-gradient(90deg, hsl(199 89% 48% / 0.12) 0%, hsl(var(--primary) / 0.08) 100%)'
              }}>
                <CardTitle className="text-foreground flex items-center gap-2 text-lg sm:text-xl">
                  <FileText className="w-5 h-5 text-sky-600 dark:text-sky-400" />
                  Лицензии
                  <span className="ml-auto text-sm font-normal text-muted-foreground">
                    Записей: {profile.license_records.length}
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 sm:space-y-4 p-4 sm:p-6">
                {profile.license_records.map((record, idx) => (
                  <div key={`${record.license_id}-${idx}`} className="glass p-3 sm:p-4 rounded-lg hover:bg-sky-500/5 transition-all duration-300 space-y-3">
                    <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2">
                      <div>
                        <span className="text-xs sm:text-sm text-muted-foreground font-medium block mb-1">Вид деятельности</span>
                        <p className="text-foreground font-semibold text-sm sm:text-base leading-relaxed">
                          {record.activity_type_name || "Не указано"}
                        </p>
                      </div>
                      {record.generated_number && (
                        <span className="font-mono text-xs glass px-2 py-1 rounded bg-sky-500/10 text-sky-700 dark:text-sky-300 font-semibold w-fit">
                          № {record.generated_number}
                        </span>
                      )}
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                      {record.holder_name && (
                        <div>
                          <span className="text-muted-foreground block">Лицензиат</span>
                          <span className="text-foreground font-medium">{record.holder_name}</span>
                        </div>
                      )}
                      {record.activity_is_active !== undefined && record.activity_is_active !== null && (
                        <div>
                          <span className="text-muted-foreground block">Статус</span>
                          <span className={`font-medium ${record.activity_is_active ? "text-green-600 dark:text-green-400" : "text-muted-foreground"}`}>
                            {record.activity_is_active ? "Активна" : "Не активна"}
                          </span>
                        </div>
                      )}
                      {record.activity_date_start && (
                        <div>
                          <span className="text-muted-foreground block">Начало</span>
                          <span className="text-foreground font-medium">{formatDate(record.activity_date_start)}</span>
                        </div>
                      )}
                      {record.activity_date_end && (
                        <div>
                          <span className="text-muted-foreground block">Окончание</span>
                          <span className="text-foreground font-medium">{formatDate(record.activity_date_end)}</span>
                        </div>
                      )}
                    </div>

                  </div>
                ))}
              </CardContent>
            </Card>
            </SectionCard>
          )}

          {profile.inspection_plan_records && profile.inspection_plan_records.length > 0 && (
            <SectionCard>
            <Card className="glass shadow-card hover:shadow-glow transition-all duration-300 border-amber-500/25">
              <CardHeader className="rounded-t-lg" style={{
                background: 'linear-gradient(90deg, hsl(38 92% 50% / 0.12) 0%, hsl(var(--primary) / 0.08) 100%)'
              }}>
                <CardTitle className="text-foreground flex items-center gap-2 text-lg sm:text-xl">
                  <ClipboardCheck className="w-5 h-5 text-amber-600 dark:text-amber-400" />
                  План выборочных проверок
                  <span className="ml-auto text-sm font-normal text-muted-foreground">
                    Записей: {profile.inspection_plan_records.length}
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 sm:space-y-4 p-4 sm:p-6">
                {profile.inspection_plan_records.map((record, idx) => (
                  <div key={`${record.plan_period}-${record.plan_item_no}-${record.controller_unp}-${idx}`} className="glass p-3 sm:p-4 rounded-lg hover:bg-amber-500/5 transition-all duration-300 space-y-3">
                    <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2">
                      <div>
                        <span className="text-xs sm:text-sm text-muted-foreground font-medium block mb-1">Контролирующий орган</span>
                        <p className="text-foreground font-semibold text-sm sm:text-base leading-relaxed">
                          {record.controller_authority || "Не указан"}
                        </p>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                      {record.plan_item_no !== undefined && record.plan_item_no !== null && (
                        <div>
                          <span className="text-muted-foreground block">№ пункта в плане</span>
                          <span className="text-foreground font-medium">{record.plan_item_no}</span>
                        </div>
                      )}
                      {record.plan_period && (
                        <div>
                          <span className="text-muted-foreground block">Период</span>
                          <span className="text-foreground font-medium">
                            {formatInspectionPeriod(record.plan_period, record.plan_year, record.plan_half)}
                          </span>
                        </div>
                      )}
                      {record.start_month && (
                        <div>
                          <span className="text-muted-foreground block">Месяц начала</span>
                          <span className="text-foreground font-medium">{record.start_month}</span>
                        </div>
                      )}
                      {record.source_region && (
                        <div>
                          <span className="text-muted-foreground block">Регион плана</span>
                          <span className="text-foreground font-medium">{formatInspectionRegion(record.source_region)}</span>
                        </div>
                      )}
                      {record.approving_authority && (
                        <div>
                          <span className="text-muted-foreground block">Утвердивший орган</span>
                          <span className="text-foreground font-medium">{record.approving_authority}</span>
                        </div>
                      )}
                      {record.controller_unp && (
                        <div>
                          <span className="text-muted-foreground block">УНП контролирующего органа</span>
                          <span className="text-foreground font-medium">{record.controller_unp}</span>
                        </div>
                      )}
                      {record.executor_phone && (
                        <div>
                          <span className="text-muted-foreground block">Телефон исполнителя</span>
                          <span className="text-foreground font-medium">{record.executor_phone}</span>
                        </div>
                      )}
                    </div>

                    {record.plan_title && (
                      <div className="text-sm">
                        <span className="text-muted-foreground block">План</span>
                        <span className="text-foreground font-medium">{record.plan_title}</span>
                      </div>
                    )}
                  </div>
                ))}
              </CardContent>
            </Card>
            </SectionCard>
          )}

          {profile.belltpp_own_certificates && profile.belltpp_own_certificates.length > 0 && (
            <SectionCard>
            <Card className="glass shadow-card hover:shadow-glow transition-all duration-300 border-violet-500/25">
              <CardHeader className="rounded-t-lg" style={{
                background: 'linear-gradient(90deg, hsl(262 83% 58% / 0.12) 0%, hsl(var(--primary) / 0.08) 100%)'
              }}>
                <CardTitle className="text-foreground flex items-center gap-2 text-lg sm:text-xl">
                  <Award className="w-5 h-5 text-violet-600 dark:text-violet-400" />
                  Сертификаты собственного производства БелТПП
                  <span className="ml-auto text-sm font-normal text-muted-foreground">
                    Записей: {profile.belltpp_own_certificates.length}
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 sm:space-y-4 p-4 sm:p-6">
                {profile.belltpp_own_certificates.map((record, idx) => {
                  const products = record.products || [];
                  const productKey = `${record.cert_number}-${record.blank_number || ""}-${idx}`;
                  const productsExpanded = expandedBeltppProducts.has(productKey);
                  const visibleProducts = productsExpanded ? products : products.slice(0, 6);
                  return (
                    <div key={productKey} className="glass p-3 sm:p-4 rounded-lg hover:bg-violet-500/5 transition-all duration-300 space-y-3">
                      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2">
                        <div>
                          <span className="text-xs sm:text-sm text-muted-foreground font-medium block mb-1">Сертификат</span>
                          <p className="text-foreground font-semibold text-sm sm:text-base leading-relaxed">
                            {record.cert_number}
                          </p>
                        </div>
                        {record.verify_url && (
                          <a
                            href={record.verify_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-2 text-primary hover:text-primary/80 font-semibold underline decoration-primary/30 hover:decoration-primary transition-all duration-300 text-sm"
                          >
                            <ExternalLink className="h-4 w-4" />
                            Проверить
                          </a>
                        )}
                      </div>

                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                        {record.blank_number && (
                          <div>
                            <span className="text-muted-foreground block">Бланк</span>
                            <span className="text-foreground font-medium">{record.blank_number}</span>
                          </div>
                        )}
                        {record.issue_date && (
                          <div>
                            <span className="text-muted-foreground block">Дата выдачи</span>
                            <span className="text-foreground font-medium">{formatDate(record.issue_date)}</span>
                          </div>
                        )}
                        {record.valid_until && (
                          <div>
                            <span className="text-muted-foreground block">Действителен до</span>
                            <span className="text-foreground font-medium">{formatDate(record.valid_until)}</span>
                          </div>
                        )}
                        {products.length > 0 && (
                          <div>
                            <span className="text-muted-foreground block">Продукции/услуг</span>
                            <span className="text-foreground font-medium">{products.length}</span>
                          </div>
                        )}
                      </div>

                      {products.length > 0 && (
                        <div className="space-y-2">
                          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                            <span className="text-muted-foreground block text-sm">Продукция / услуги</span>
                            {products.length > 6 && (
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                className="glass hover:bg-violet-500/10 transition-all duration-300 text-xs w-fit"
                                onClick={() => toggleBeltppProducts(productKey)}
                              >
                                {productsExpanded ? "Скрыть позиции" : `Показать все позиции (${products.length})`}
                              </Button>
                            )}
                          </div>
                          <div className="space-y-2">
                            {visibleProducts.map((product, productIdx) => (
                              <div key={`${record.cert_number}-product-${productIdx}`} className="rounded-md bg-background/60 border border-border/50 p-2 text-sm">
                                <div className="text-foreground font-medium leading-relaxed">
                                  {product.name || "Не указано"}
                                </div>
                                {product.code && (
                                  <div className="mt-1 text-xs text-muted-foreground">
                                    Код: {product.code}
                                  </div>
                                )}
                              </div>
                            ))}
                            {products.length > 6 && (
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                className="glass hover:bg-violet-500/10 transition-all duration-300 text-xs"
                                onClick={() => toggleBeltppProducts(productKey)}
                              >
                                {productsExpanded ? "Скрыть позиции" : `Показать все позиции (${products.length})`}
                              </Button>
                            )}
                          </div>
                        </div>
                      )}

                    </div>
                  );
                })}
              </CardContent>
            </Card>
            </SectionCard>
          )}

          {profile.trade_registry_records && profile.trade_registry_records.length > 0 && (
            <SectionCard>
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
            </SectionCard>
          )}

          {/* Банкротство */}
          {profile.bankrot_cases && (
            <SectionCard>
            <Card className={`glass shadow-card hover:shadow-glow transition-all duration-300 ${
              profile.bankrot_cases.length > 0 ? "border-orange-500/30" : "border-emerald-500/25"
            }`}>
              <CardHeader className="rounded-t-lg" style={{
                background: profile.bankrot_cases.length > 0
                  ? 'linear-gradient(90deg, hsl(25 95% 53% / 0.12) 0%, hsl(var(--destructive) / 0.08) 100%)'
                  : 'linear-gradient(90deg, hsl(142 76% 36% / 0.10) 0%, hsl(var(--primary) / 0.06) 100%)'
              }}>
                <CardTitle className="text-foreground flex items-center gap-2 text-lg sm:text-xl">
                  {profile.bankrot_cases.length > 0
                    ? <AlertTriangle className="w-5 h-5 text-orange-500" />
                    : <ShieldCheck className="w-5 h-5 text-emerald-500" />}
                  Банкротство
                  <span className="ml-auto text-sm font-normal text-muted-foreground">
                    {profile.bankrot_cases.length === 0
                      ? "не найдено"
                      : `${profile.bankrot_cases.length} ${profile.bankrot_cases.length === 1 ? "дело" : profile.bankrot_cases.length < 5 ? "дела" : "дел"}`}
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 sm:space-y-4 p-4 sm:p-6">
                {profile.bankrot_cases.length === 0 && (
                  <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-4">
                    <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                      <ShieldCheck className="h-4 w-4 text-emerald-500" />
                      Дел о банкротстве по этому УНП не найдено
                    </div>
                    {risk?.coverage?.sources.find((source) => source.code === "bankruptcy")?.checked_at && (
                      <div className="mt-2 text-xs text-muted-foreground">
                        Реестр проверен: {formatDate(risk.coverage.sources.find((source) => source.code === "bankruptcy")?.checked_at ?? undefined)}
                      </div>
                    )}
                  </div>
                )}
                {profile.bankrot_cases.map((c) => {
                  const isActive = !c.end_date;
                  const fullCase = bankruptcyData?.cases.find((item) => item.case_id === c.case_id);
                  const successfulDatasets = fullCase?.datasets.filter(
                    (dataset) => getBankrotPayloadCount(dataset.payload) > 0
                  ).length ?? 0;
                  const failedDatasets = fullCase?.datasets.filter(
                    (dataset) => dataset.fetch_error
                  ).length ?? 0;
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

                      {showBankruptcyDetails && fullCase && (
                        <div className="space-y-2 border-t border-border/60 pt-3">
                          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                            <div className="rounded-lg border border-border/60 bg-background/60 p-3">
                              <div className="text-xl font-semibold">{fullCase.datasets.length}</div>
                              <div className="text-xs text-muted-foreground">разделов найдено</div>
                            </div>
                            <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-3">
                              <div className="text-xl font-semibold text-emerald-600 dark:text-emerald-400">
                                {successfulDatasets}
                              </div>
                              <div className="text-xs text-muted-foreground">с данными</div>
                            </div>
                            <div className={`rounded-lg border p-3 ${
                              failedDatasets
                                ? "border-destructive/30 bg-destructive/5"
                                : "border-emerald-500/30 bg-emerald-500/5"
                            }`}>
                              <div className={`text-xl font-semibold ${
                                failedDatasets
                                  ? "text-destructive"
                                  : "text-emerald-600 dark:text-emerald-400"
                              }`}>
                                {failedDatasets}
                              </div>
                              <div className="text-xs text-muted-foreground">ошибок обновления</div>
                            </div>
                            <div className="rounded-lg border border-border/60 bg-background/60 p-3">
                              <div className="text-xl font-semibold">
                                {fullCase.manager_name ? "Да" : "—"}
                              </div>
                              <div className="text-xs text-muted-foreground">управляющий определён</div>
                            </div>
                          </div>
                          <BankrotDataView
                            detailData={fullCase.detail_data}
                            listData={fullCase.list_data}
                            judgementsGroup={fullCase.judgements_group}
                            datasets={fullCase.datasets}
                          />
                        </div>
                      )}
                    </div>
                  );
                })}
                {profile.bankrot_cases.length > 0 && (
                  <>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={toggleBankruptcyDetails}
                      disabled={bankruptcyLoading}
                      className="w-full sm:w-auto"
                    >
                      {bankruptcyLoading
                        ? "Загрузка сведений..."
                        : showBankruptcyDetails
                          ? "Скрыть подробные сведения"
                          : "Показать все сведения реестра"}
                    </Button>
                    {showBankruptcyDetails && bankruptcyError && (
                      <p className="text-sm text-destructive">{bankruptcyError}</p>
                    )}
                  </>
                )}
              </CardContent>
            </Card>
            </SectionCard>
          )}

          <SectionCard>
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
                    В доступных срезах записей о налоговой задолженности по этой компании нет.
                  </p>
                  {taxDebtData.latest_global_slice_date && (
                    <p className="text-xs text-muted-foreground">
                      Актуальность общего среза МНС: {formatDate(taxDebtData.latest_global_slice_date)}
                    </p>
                  )}
                </div>
              )}

              {taxDebtData && taxDebtData.count > 0 && (
                <div className="space-y-4">
                  <div className="grid gap-2 text-sm sm:grid-cols-3">
                    <div className="rounded-lg border border-border/60 bg-background/50 p-3">
                      <div className="text-xs text-muted-foreground">Актуальная задолженность</div>
                      <div className={`mt-1 font-semibold ${taxDebtData.has_current_debt ? "text-destructive" : "text-emerald-600"}`}>
                        {taxDebtData.has_current_debt ? `${taxDebtData.current_count ?? 0} записей` : "Не найдена"}
                      </div>
                    </div>
                    <div className="rounded-lg border border-border/60 bg-background/50 p-3">
                      <div className="text-xs text-muted-foreground">История по компании</div>
                      <div className="mt-1 font-semibold text-foreground">{taxDebtData.count} записей</div>
                    </div>
                    <div className="rounded-lg border border-border/60 bg-background/50 p-3">
                      <div className="text-xs text-muted-foreground">Актуальность данных МНС</div>
                      <div className="mt-1 font-semibold text-foreground">
                        {formatDate(taxDebtData.latest_global_slice_date)}
                      </div>
                    </div>
                  </div>

                  {taxDebtData.count > taxDebtData.items.length && (
                    <p className="text-xs text-muted-foreground">
                      Показаны первые {taxDebtData.items.length} из {taxDebtData.count} записей.
                    </p>
                  )}

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
          </SectionCard>

          {relatedData && (relatedData.by_address.length > 0 || relatedData.by_contact.length > 0) && (
            <SectionCard>
            <Card className="glass shadow-card hover:shadow-glow transition-all duration-300 border-fuchsia-500/25">
              <CardHeader className="rounded-t-lg" style={{
                background: 'linear-gradient(90deg, hsl(292 70% 55% / 0.1) 0%, hsl(var(--primary) / 0.08) 100%)'
              }}>
                <CardTitle className="text-foreground flex items-center gap-2 text-lg sm:text-xl">
                  <Users className="w-5 h-5 text-fuchsia-600 dark:text-fuchsia-400" />
                  Связанные компании
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4 p-4 sm:p-6">
                {relatedData.by_address.length > 0 && (
                  <div>
                    <div className="text-xs sm:text-sm text-muted-foreground font-medium mb-2 flex items-center gap-2">
                      <Building2 className="w-4 h-4" />
                      По тому же адресу ({relatedData.by_address.length})
                    </div>
                    <div className="space-y-2">
                      {relatedData.by_address.map((item) => (
                        <Link
                          key={`addr-${item.unp}`}
                          to={`/company/${item.unp}`}
                          className="glass p-3 rounded-lg hover:bg-fuchsia-500/5 transition-all duration-300 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1 group"
                        >
                          <span className="text-foreground font-medium text-sm group-hover:text-fuchsia-600 dark:group-hover:text-fuchsia-400 transition-colors">
                            {item.name || `УНП ${item.unp}`}
                          </span>
                          <span className="text-xs text-muted-foreground flex-shrink-0">УНП {item.unp}</span>
                        </Link>
                      ))}
                    </div>
                  </div>
                )}

                {relatedData.by_contact.length > 0 && (
                  <div>
                    <div className="text-xs sm:text-sm text-muted-foreground font-medium mb-2 flex items-center gap-2">
                      <Phone className="w-4 h-4" />
                      По общему телефону/email ({relatedData.by_contact.length})
                    </div>
                    <div className="space-y-2">
                      {relatedData.by_contact.map((item, idx) => (
                        <Link
                          key={`contact-${item.unp}-${idx}`}
                          to={`/company/${item.unp}`}
                          className="glass p-3 rounded-lg hover:bg-fuchsia-500/5 transition-all duration-300 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1 group"
                        >
                          <span className="text-foreground font-medium text-sm group-hover:text-fuchsia-600 dark:group-hover:text-fuchsia-400 transition-colors">
                            {item.name || `УНП ${item.unp}`}
                          </span>
                          <span className="text-xs text-muted-foreground flex items-center gap-1 flex-shrink-0">
                            {item.matched_type === "email" ? <Mail className="w-3 h-3" /> : <Phone className="w-3 h-3" />}
                            {item.matched_value}
                          </span>
                        </Link>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
            </SectionCard>
          )}

          {profile.gias_contracts && (
            <SectionCard>
              <GiasContractsSection
                contracts={profile.gias_contracts}
                companyUnp={profile.unp}
              />
            </SectionCard>
          )}
          </motion.div>
        )}
      </motion.div>
    </div>
  );
};

export default Company;
