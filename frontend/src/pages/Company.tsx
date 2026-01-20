import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getCompanyProfile, CompanyProfile } from "@/lib/api";

const fieldLabels: Record<string, string> = {
  status: "Статус",
  status_code: "Код статуса",
  address: "Адрес",
  registration_date: "Дата регистрации",
  last_update: "Дата обновления",
  oked: "ОКЭД",
  oked_name: "Наименование ОКЭД",
  opf: "ОПФ",
  opf_name: "Наименование ОПФ",
  region: "Область",
  district: "Район",
  city: "Город",
  inspectorate: "Инспекция",
  kfv: "КФВ",
  kfv_name: "Наименование КФВ",
  kfsp: "КФСП",
  kfsp_name: "Наименование КФСП",
  medium: "Средняя численность",
  medium_name: "Наименование численности",
};

const Company = () => {
  const { unp } = useParams();
  const [profile, setProfile] = useState<CompanyProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

  return (
    <div className="min-h-screen bg-background px-4 py-10">
      <div className="max-w-4xl mx-auto space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-3xl font-bold text-foreground">
              {profile?.name || "Профиль компании"}
            </h1>
            {unp && <p className="text-muted-foreground mt-1">УНП {unp}</p>}
          </div>
          {unp && (
            <div className="flex gap-2">
              <Link to={`/company/${unp}/raw`}>
                <Button variant="outline">Raw данные</Button>
              </Link>
              <Link to={`/company/${unp}/compare`}>
                <Button variant="outline">Сравнение API</Button>
              </Link>
            </div>
          )}
        </div>

        {loading && <p className="text-muted-foreground">Загрузка...</p>}
        {error && (
          <Card className="border-destructive">
            <CardContent className="py-4 text-destructive">{error}</CardContent>
          </Card>
        )}

        {profile && (
          <Card>
            <CardHeader>
              <CardTitle>Основные данные</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {Object.entries(fieldLabels).map(([key, label]) => {
                const value = (profile as Record<string, string | undefined>)[key];
                if (!value) {
                  return null;
                }
                return (
                  <div key={key} className="flex flex-col gap-1">
                    <span className="text-sm text-muted-foreground">{label}</span>
                    <span className="text-foreground">{value}</span>
                  </div>
                );
              })}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
};

export default Company;
