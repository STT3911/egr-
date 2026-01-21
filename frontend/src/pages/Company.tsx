import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getCompanyProfile, CompanyProfile } from "@/lib/api";

const fieldLabels: Record<string, string> = {
  current_name_ru: "Полное название",
  current_short_name_ru: "Краткое название",
  current_name_by: "Название на белорусском",
  unp: "УНП",
  current_status_code: "Код статуса",
  registration_date: "Дата регистрации",
  liquidation_date: "Дата ликвидации",
  entity_type_id: "Тип субъекта",
  creation_method_id: "Способ создания",
  creation_decision_no: "Номер решения о создании",
  liquidation_decision_no: "Номер решения о ликвидации",
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
          <>
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

          {/* История названий */}
          {profile.names && profile.names.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>История названий</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {profile.names.map((name, idx) => (
                  <div key={idx} className="border-b pb-3 last:border-0">
                    <div className="space-y-2">
                      {name.full_name_ru && (
                        <div>
                          <span className="text-sm text-muted-foreground">Полное название:</span>
                          <p className="text-foreground">{name.full_name_ru}</p>
                        </div>
                      )}
                      {name.short_name_ru && (
                        <div>
                          <span className="text-sm text-muted-foreground">Краткое название:</span>
                          <p className="text-foreground">{name.short_name_ru}</p>
                        </div>
                      )}
                      <div className="text-xs text-muted-foreground">
                        {name.valid_from && `С ${name.valid_from}`}
                        {name.valid_to && ` по ${name.valid_to}`}
                        {!name.valid_to && " (действует)"}
                      </div>
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {/* История адресов */}
          {profile.addresses && profile.addresses.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>История адресов</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {profile.addresses.map((addr, idx) => (
                  <div key={idx} className="border-b pb-3 last:border-0">
                    <p className="text-foreground">{addr.full_address}</p>
                    {(addr.region || addr.district) && (
                      <p className="text-sm text-muted-foreground">
                        {[addr.region, addr.district].filter(Boolean).join(", ")}
                      </p>
                    )}
                    <div className="text-xs text-muted-foreground mt-1">
                      {addr.valid_from && `С ${addr.valid_from}`}
                      {addr.valid_to && ` по ${addr.valid_to}`}
                      {!addr.valid_to && " (действует)"}
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {/* История ВЭД */}
          {profile.ved && profile.ved.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Виды экономической деятельности</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {profile.ved.map((v, idx) => (
                  <div key={idx} className="border-b pb-3 last:border-0">
                    <div className="flex gap-2">
                      <span className="font-mono text-sm">{v.ved_code}</span>
                      <span className="text-foreground">{v.ved_name}</span>
                    </div>
                    <div className="text-xs text-muted-foreground mt-1">
                      {v.valid_from && `С ${v.valid_from}`}
                      {v.valid_to && ` по ${v.valid_to}`}
                      {!v.valid_to && " (действует)"}
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {/* Контактная информация */}
          {profile.contacts && profile.contacts.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Контактная информация</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {profile.contacts.map((contact, idx) => (
                  <div key={idx} className="space-y-2">
                    {contact.phone && (
                      <div>
                        <span className="text-sm text-muted-foreground">Телефон:</span>
                        <p className="text-foreground">{contact.phone}</p>
                      </div>
                    )}
                    {contact.email && (
                      <div>
                        <span className="text-sm text-muted-foreground">Email:</span>
                        <p className="text-foreground">{contact.email}</p>
                      </div>
                    )}
                    {contact.website && (
                      <div>
                        <span className="text-sm text-muted-foreground">Сайт:</span>
                        <p className="text-foreground">
                          <a href={contact.website} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
                            {contact.website}
                          </a>
                        </p>
                      </div>
                    )}
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
        </>
        )}
      </div>
    </div>
  );
};

export default Company;
