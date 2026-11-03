import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { CompanyEventTimeline } from "@/components/CompanyEventTimeline";
import { Header } from "@/components/layout/Header";
import { getCompanyProfile } from "@/lib/api";

export default function CompanyEvents() {
  const { unp = "" } = useParams();
  const profile = useQuery({
    queryKey: ["company-events-profile", unp],
    queryFn: () => getCompanyProfile(unp),
    retry: false,
  });

  return (
    <div className="min-h-screen bg-background px-4 pb-12 pt-28">
      <Header />
      <main className="mx-auto max-w-4xl space-y-5">
        <Link to={`/company/${unp}`} className="text-sm font-medium text-primary hover:underline">
          Назад к карточке
        </Link>
        <h1 className="break-words text-2xl font-semibold">
          {profile.data?.current_short_name_ru || profile.data?.current_name_ru || `УНП ${unp}`}
        </h1>
        {profile.isPending && <p role="status">Загружаем события…</p>}
        {profile.isError && (
          <div role="alert" className="space-y-2">
            <p>Не удалось загрузить события.</p>
            <button type="button" className="text-primary hover:underline" onClick={() => void profile.refetch()}>
              Повторить
            </button>
          </div>
        )}
        {profile.data && <CompanyEventTimeline key={unp} profile={profile.data} full />}
      </main>
    </div>
  );
}
