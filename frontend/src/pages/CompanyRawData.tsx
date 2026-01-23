import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ArrowLeft } from "lucide-react";
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
        {/* Mobile decorative elements */}
        <div className="sm:hidden absolute top-10 right-10 w-32 h-32 rounded-full blur-2xl animate-pulse dark:opacity-20" style={{
          backgroundColor: 'hsl(var(--primary) / 0.06)'
        }} />
        <div className="sm:hidden absolute bottom-10 left-10 w-24 h-24 rounded-full blur-xl animate-pulse dark:opacity-25" style={{
          backgroundColor: 'hsl(var(--accent) / 0.05)',
          animationDelay: "1.5s"
        }} />
      </div>

      <div className="max-w-5xl mx-auto space-y-6 relative z-10">
        {/* Navigation Buttons */}
        <div className="flex items-center justify-start gap-4">
          <Link to={unp ? `/company/${unp}` : "/"}>
            <Button variant="ghost" className="flex items-center gap-2 glass hover:bg-primary/10 dark:hover:bg-primary/20 transition-all duration-300">
              <ArrowLeft className="w-4 h-4" />
              К компании
            </Button>
          </Link>
          <Link to="/">
            <Button variant="ghost" className="flex items-center gap-2 glass hover:bg-primary/10 dark:hover:bg-primary/20 transition-all duration-300">
              <ArrowLeft className="w-4 h-4" />
              На главную
            </Button>
          </Link>
        </div>

        <div className="space-y-2">
          <h1 className="text-2xl sm:text-3xl md:text-4xl font-bold text-foreground">Raw данные</h1>
          {unp && (
            <div className="flex items-center gap-2">
              <span className="glass px-3 py-1 rounded-full text-sm text-primary font-medium">
                УНП {unp}
              </span>
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
          <Card className="glass shadow-card hover:shadow-glow transition-all duration-300 border-primary/20">
            <CardHeader className="rounded-t-lg" style={{
              background: 'linear-gradient(90deg, hsl(var(--primary) / 0.1) 0%, hsl(var(--accent) / 0.1) 100%)'
            }}>
              <CardTitle className="text-gradient flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-primary animate-pulse"></div>
                Ответ API
              </CardTitle>
            </CardHeader>
            <CardContent className="p-6">
              <div className="glass p-4 rounded-lg bg-secondary/30">
                <pre className="text-sm overflow-x-auto whitespace-pre-wrap text-foreground font-mono leading-relaxed">
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
