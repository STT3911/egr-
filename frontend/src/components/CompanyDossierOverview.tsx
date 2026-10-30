import { AlertTriangle, BadgeCheck, Building2, CalendarDays, CheckCircle2, FileCheck2, Landmark, Mail, ShieldCheck, Store, Users } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { CompanyProfile, CompanyRisk, CompanyTaxDebtResponse } from "@/lib/api";

type Tone = "good" | "attention" | "neutral";

const toneClasses: Record<Tone, string> = {
  good: "border-emerald-500/25 bg-emerald-500/8 text-emerald-700 dark:text-emerald-300",
  attention: "border-amber-500/30 bg-amber-500/10 text-amber-800 dark:text-amber-200",
  neutral: "border-border/70 bg-background/50 text-foreground",
};

const sourceLabels: Record<string, string> = {
  egr: "ЕГР", grp: "ГРП", gias: "ГИАС", mart: "МАРТ", pvt: "ПВТ",
  licenses: "Лицензии", inspections: "Проверки", belltpp: "БелТПП", tax: "МНС",
};

type Props = {
  profile: CompanyProfile;
  risk: CompanyRisk | null;
  taxDebt: CompanyTaxDebtResponse | null;
};

function Metric({ icon: Icon, label, value, tone = "neutral" }: { icon: typeof Building2; label: string; value: string | number; tone?: Tone }) {
  return (
    <div className={`rounded-xl border p-3 ${toneClasses[tone]}`}>
      <Icon className="h-4 w-4 opacity-75" aria-hidden="true" />
      <div className="mt-2 text-[11px] uppercase tracking-wide opacity-75">{label}</div>
      <div className="mt-1 text-lg font-semibold">{value}</div>
    </div>
  );
}

export function CompanyDossierOverview({ profile, risk, taxDebt }: Props) {
  const currentDebt = taxDebt?.current_count ?? 0;
  const taxHistory = taxDebt?.count ?? 0;
  const activeLicenses = profile.license_records?.filter(item => item.activity_is_active).length ?? 0;
  const bankrotCount = profile.bankrot_cases?.length ?? 0;
  const contactsCount = profile.contacts_aggregated?.length || profile.contacts?.length || 0;
  const riskAttention = risk?.factors?.filter(factor => factor.severity === "critical" || factor.severity === "high").slice(0, 4) ?? [];
  const hasAttention = currentDebt > 0 || bankrotCount > 0 || riskAttention.length > 0;
  const domains = [
    ["ЕГР", Boolean(profile.current_status_name || profile.addresses?.length), "egr"],
    ["ГРП", Boolean(profile.current_status_name), "grp"],
    ["Контакты", contactsCount > 0, "egr"],
    ["ГИАС", Boolean(profile.gias_accreditation || profile.gias_contracts?.length), "gias"],
    ["МАРТ", (profile.trade_registry_records?.length ?? 0) > 0, "mart"],
    ["Лицензии", (profile.license_records?.length ?? 0) > 0, "licenses"],
    ["Проверки", (profile.inspection_plan_records?.length ?? 0) > 0, "inspections"],
    ["БелТПП", (profile.belltpp_own_certificates?.length ?? 0) > 0, "belltpp"],
  ] as const;

  return (
    <Card id="egr-section" className="scroll-mt-24 overflow-hidden border-primary/20 bg-card/95 shadow-card">
      <CardHeader className="border-b border-border/60 bg-gradient-to-r from-primary/10 via-accent/8 to-transparent">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <CardTitle className="flex items-center gap-2 text-lg sm:text-xl">
              <ShieldCheck className="h-5 w-5 text-primary" />
              Экспресс-сводка досье
            </CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              Ключевые сигналы по доступным источникам. Судебный блок намеренно не включён.
            </p>
          </div>
          <Badge variant="outline" className={hasAttention ? toneClasses.attention : toneClasses.good}>
            {hasAttention ? "Требует внимания" : "Критичных сигналов нет"}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-5 p-4 sm:p-6">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
          <Metric icon={Building2} label="Статус" value={profile.current_status_name || "—"} tone={profile.current_status_name?.toLowerCase().includes("ликвид") ? "attention" : "good"} />
          <Metric icon={CalendarDays} label="Возраст" value={profile.registration_date ? new Date(profile.registration_date).getFullYear() : "—"} />
          <Metric icon={AlertTriangle} label="Долги МНС" value={currentDebt || taxHistory ? `${currentDebt} акт. / ${taxHistory} ист.` : "Нет"} tone={currentDebt ? "attention" : "good"} />
          <Metric icon={FileCheck2} label="Лицензии" value={`${activeLicenses} актив.`} tone={activeLicenses ? "good" : "neutral"} />
          <Metric icon={Store} label="Торговля" value={profile.trade_registry_records?.length ?? 0} />
          <Metric icon={Mail} label="Контакты" value={contactsCount} />
        </div>

        <div className="grid gap-4 lg:grid-cols-[1.15fr_0.85fr]">
          <section className="rounded-2xl border border-border/60 bg-background/45 p-4">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold">
              <AlertTriangle className={`h-4 w-4 ${hasAttention ? "text-amber-600" : "text-emerald-600"}`} />
              Что проверить первым
            </div>
            {riskAttention.length || currentDebt || bankrotCount ? (
              <div className="space-y-2">
                {currentDebt > 0 && <div className="rounded-lg border border-amber-500/25 bg-amber-500/8 px-3 py-2 text-sm">Есть текущая задолженность по налогам: {currentDebt} акт.</div>}
                {bankrotCount > 0 && <div className="rounded-lg border border-red-500/25 bg-red-500/8 px-3 py-2 text-sm">Найдены записи о банкротстве: {bankrotCount}</div>}
                {riskAttention.map(factor => <div key={factor.code} className="rounded-lg border border-border/60 bg-card/60 px-3 py-2 text-sm">{factor.title}</div>)}
              </div>
            ) : (
              <div className="flex items-center gap-2 text-sm text-muted-foreground"><CheckCircle2 className="h-4 w-4 text-emerald-600" /> Критичных сигналов в доступных данных нет.</div>
            )}
          </section>

          <section className="rounded-2xl border border-border/60 bg-background/45 p-4">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold"><BadgeCheck className="h-4 w-4 text-primary" /> Покрытие источников</div>
            <div className="flex flex-wrap gap-2">
              {domains.map(([label, present, source]) => <Badge key={label} variant="outline" className={present ? toneClasses.good : "border-border/60 text-muted-foreground"}>{label}{present ? " · есть" : " · нет"}</Badge>)}
            </div>
            <p className="mt-3 text-xs leading-relaxed text-muted-foreground">Наличие блока не означает, что источник обновлён сегодня. Дата и источник указаны внутри соответствующей секции.</p>
          </section>
        </div>

        <div className="grid gap-3 sm:grid-cols-3">
          <div className="rounded-xl border border-border/60 bg-card/50 p-3"><div className="flex items-center gap-2 text-xs text-muted-foreground"><Users className="h-3.5 w-3.5" /> Руководители</div><div className="mt-2 text-xl font-semibold">{profile.leadership_observations?.length ?? 0}</div></div>
          <div className="rounded-xl border border-border/60 bg-card/50 p-3"><div className="flex items-center gap-2 text-xs text-muted-foreground"><Landmark className="h-3.5 w-3.5" /> ГИАС-контракты</div><div className="mt-2 text-xl font-semibold">{profile.gias_contracts?.length ?? 0}</div></div>
          <div className="rounded-xl border border-border/60 bg-card/50 p-3"><div className="flex items-center gap-2 text-xs text-muted-foreground"><FileCheck2 className="h-3.5 w-3.5" /> Сертификаты БелТПП</div><div className="mt-2 text-xl font-semibold">{profile.belltpp_own_certificates?.length ?? 0}</div></div>
        </div>
      </CardContent>
    </Card>
  );
}
