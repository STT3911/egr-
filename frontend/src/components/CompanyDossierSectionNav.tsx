import { ArrowDown, Building2, Store } from "lucide-react";
import { Card } from "@/components/ui/card";
import type { CompanyProfile } from "@/lib/api";

export function CompanyDossierSectionNav({ profile }: { profile: CompanyProfile }) {
  const tradeCount = profile.trade_registry_records?.length ?? 0;
  const egrSignals = [
    profile.current_status_name,
    profile.addresses?.length ? `${profile.addresses.length} адрес.` : null,
    profile.contacts_aggregated?.length ? `${profile.contacts_aggregated.length} конт.` : null,
  ].filter(Boolean).join(" · ") || "Основные сведения";

  return (
    <nav aria-label="Разделы досье" className="grid gap-3 sm:grid-cols-2">
      <a href="#egr-section" className="group rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2">
        <Card className="h-full border-primary/20 bg-card/80 p-4 transition-colors group-hover:border-primary/50 group-hover:bg-primary/5 sm:p-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 text-base font-semibold text-foreground"><Building2 className="h-4 w-4 text-primary" /> ЕГР</div>
              <p className="mt-2 text-sm text-muted-foreground">{egrSignals}</p>
            </div>
            <ArrowDown className="h-4 w-4 text-primary transition-transform group-hover:translate-y-1" aria-hidden="true" />
          </div>
        </Card>
      </a>
      <a href="#trade-registry-section" className="group rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2">
        <Card className="h-full border-amber-500/25 bg-card/80 p-4 transition-colors group-hover:border-amber-500/50 group-hover:bg-amber-500/5 sm:p-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 text-base font-semibold text-foreground"><Store className="h-4 w-4 text-amber-600 dark:text-amber-400" /> Торговый реестр</div>
              <p className="mt-2 text-sm text-muted-foreground">{tradeCount ? `${tradeCount} записей МАРТ` : "Записей пока нет"}</p>
            </div>
            <ArrowDown className="h-4 w-4 text-amber-600 transition-transform group-hover:translate-y-1" aria-hidden="true" />
          </div>
        </Card>
      </a>
    </nav>
  );
}
