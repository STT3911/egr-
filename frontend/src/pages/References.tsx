import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { Header } from "@/components/layout/Header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { listReferenceTypes } from "@/lib/api";

const References = () => {
  const [types, setTypes] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);

      try {
        const data = await listReferenceTypes();
        setTypes(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Ошибка загрузки справочников");
      } finally {
        setLoading(false);
      }
    };

    load();
  }, []);

  return (
    <div className="min-h-screen bg-background px-4 pb-12 pt-28">
      <Header />

      <div className="mx-auto max-w-5xl space-y-6">
        <div className="flex items-center justify-start">
          <Link to="/">
            <Button variant="ghost" className="flex items-center gap-2">
              <ArrowLeft className="h-4 w-4" />
              На главную
            </Button>
          </Link>
        </div>

        <div className="space-y-2">
          <h1 className="text-3xl font-extrabold text-foreground sm:text-4xl">Справочники ЕГР</h1>
          <p className="max-w-2xl text-base leading-7 text-muted-foreground">
            Список справочников оформлен в том же визуальном ритме: мягкие карточки,
            чистая иерархия и быстрый переход к нужным данным.
          </p>
        </div>

        {loading && <p className="text-muted-foreground">Загрузка...</p>}
        {error && (
          <Card className="border-destructive">
            <CardContent className="py-4 text-destructive">{error}</CardContent>
          </Card>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          {types.map((type, index) => (
            <Card key={type} className="group">
              <CardHeader>
                <div className="flex items-start justify-between gap-4">
                  <CardTitle className="text-xl">{type}</CardTitle>
                  <div className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                    {String(index + 1).padStart(2, "0")}
                  </div>
                </div>
              </CardHeader>
              <CardContent className="flex items-center justify-between gap-3">
                <div className="text-sm text-muted-foreground">
                  Открыть и посмотреть записи справочника.
                </div>
                <Link
                  to={`/references/${encodeURIComponent(type)}`}
                  className="text-sm font-semibold text-primary transition-colors group-hover:text-accent"
                >
                  Открыть
                </Link>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
};

export default References;
