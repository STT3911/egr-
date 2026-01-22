import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ArrowLeft } from "lucide-react";
import { getCompanyProfile, CompanyProfile } from "@/lib/api";

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

const Company = () => {
  const { unp } = useParams();
  const [profile, setProfile] = useState<CompanyProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeItem, setActiveItem] = useState<string | null>(null);

  const handleItemClick = (itemId: string) => {
    setActiveItem(activeItem === itemId ? null : itemId);
  };

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
    <div className="min-h-screen bg-background px-4 py-10 relative overflow-hidden" style={{
      background: 'linear-gradient(135deg, hsl(var(--background)) 0%, hsl(var(--background)) 70%, hsl(var(--secondary) / 0.2) 100%)'
    }}>
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

      <div className="max-w-4xl mx-auto space-y-6 relative z-10">
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
            <h1 className="text-2xl sm:text-3xl md:text-4xl font-bold text-foreground leading-tight">
              {profile?.name || "Профиль компании"}
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
        {error && (
          <Card className="border-destructive">
            <CardContent className="py-4 text-destructive">{error}</CardContent>
          </Card>
        )}

        {profile && (
          <>
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
                  const value = (profile as Record<string, string | undefined>)[key];
                  if (!value) {
                    return null;
                  }
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
                        activeItem === itemId || (typeof window !== 'undefined' && window.innerWidth >= 768) ? 'opacity-100 animate-fade-in-up' : 'opacity-0 group-hover:opacity-100 group-hover:animate-fade-in-up'
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
                      activeItem === itemId || (typeof window !== 'undefined' && window.innerWidth >= 768) ? 'opacity-100 animate-fade-in-up' : 'opacity-0 group-hover:opacity-100 group-hover:animate-fade-in-up'
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
                      activeItem === itemId || (typeof window !== 'undefined' && window.innerWidth >= 768) ? 'opacity-100 animate-fade-in-up' : 'opacity-0 group-hover:opacity-100 group-hover:animate-fade-in-up'
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
                      <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-2">
                        <span className="text-xs sm:text-sm text-muted-foreground font-medium">📞 Телефон:</span>
                        <p className="text-foreground font-semibold text-sm sm:text-base break-all">{contact.phone}</p>
                      </div>
                    )}
                    {contact.email && (
                      <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-2">
                        <span className="text-xs sm:text-sm text-muted-foreground font-medium">✉️ Email:</span>
                        <p className="text-foreground font-semibold text-sm sm:text-base break-all">{contact.email}</p>
                      </div>
                    )}
                    {contact.website && (
                      <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-2">
                        <span className="text-xs sm:text-sm text-muted-foreground font-medium">🌐 Сайт:</span>
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

                {/* Legend */}
                <div className="mt-4 sm:mt-6 pt-3 sm:pt-4 border-t border-border/50">
                  <div className="flex flex-wrap items-center justify-center gap-3 sm:gap-4 text-xs text-muted-foreground">
                    <div className="flex items-center gap-2">
                      <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></div>
                      <span>Действует сейчас</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="w-2 h-2 rounded-full bg-primary/60 dark:bg-primary/80"></div>
                      <span>Архивная запись</span>
                    </div>
                  </div>
                </div>
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
