import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { Header } from "@/components/layout/Header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getRawCompanyData } from "@/lib/api";

const CompanyRawData = () => {
  const { unp } = useParams();
  const [data, setData] = useState<Record<string, unknown> | null>(null);
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
        const raw = await getRawCompanyData(unp);
        setData(raw);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Ошибка загрузки данных");
      } finally {
        setLoading(false);
      }
    };

    load();
  }, [unp]);

  return (
    <div
      className="relative min-h-screen overflow-hidden bg-background px-4 pb-12 pt-28"
      style={{
        background:
          "linear-gradient(135deg, hsl(var(--background)) 0%, hsl(var(--background)) 70%, hsl(var(--secondary) / 0.2) 100%)",
      }}
    >
      <Header />

      <div className="absolute inset-0 pointer-events-none">
        <div
          className="absolute left-10 top-20 hidden h-72 w-72 rounded-full blur-3xl sm:block"
          style={{ backgroundColor: "hsl(var(--primary) / 0.08)" }}
        />
        <div
          className="absolute bottom-20 right-10 hidden h-96 w-96 rounded-full blur-3xl sm:block"
          style={{ backgroundColor: "hsl(var(--accent) / 0.06)" }}
        />
      </div>

      <div className="relative z-10 mx-auto max-w-5xl space-y-6">
        <div className="flex flex-wrap items-center gap-3">
          <Link to={unp ? `/company/${unp}` : "/"}>
            <Button variant="ghost" className="flex items-center gap-2">
              <ArrowLeft className="h-4 w-4" />
              К компании
            </Button>
          </Link>
          <Link to="/">
            <Button variant="ghost" className="flex items-center gap-2">
              <ArrowLeft className="h-4 w-4" />
              На главную
            </Button>
          </Link>
        </div>

        <div className="space-y-2">
          <h1 className="text-3xl font-extrabold text-foreground sm:text-4xl">Raw данные</h1>
          {unp && (
            <div className="glass inline-flex rounded-full px-3 py-1 text-sm font-medium text-primary">
              УНП {unp}
            </div>
          )}
        </div>

        {loading && <p className="text-muted-foreground">Загрузка...</p>}
        {error && (
          <Card className="border-destructive">
            <CardContent className="py-4 text-destructive">{error}</CardContent>
          </Card>
        )}

        {data && (
          <Card className="border-primary/20">
            <CardHeader
              className="rounded-t-[1.75rem]"
              style={{
                background:
                  "linear-gradient(90deg, hsl(var(--primary) / 0.1) 0%, hsl(var(--accent) / 0.1) 100%)",
              }}
            >
              <CardTitle className="flex items-center gap-2 text-gradient">
                <div className="h-2 w-2 rounded-full bg-primary" />
                Ответ API
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="glass rounded-[1.4rem] bg-secondary/30 p-4">
                <pre className="font-mono text-sm leading-relaxed text-foreground whitespace-pre-wrap overflow-x-auto">
                  {JSON.stringify(data, null, 2)}
                </pre>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
};

export default CompanyRawData;
