import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { compareCompanyApis } from "@/lib/api";

const CompanyCompare = () => {
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
        const raw = await compareCompanyApis(unp);
        setData(raw);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Ошибка сравнения API");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [unp]);

  return (
    <div className="min-h-screen bg-background px-4 py-10">
      <div className="max-w-5xl mx-auto space-y-6">
        <div>
          <h1 className="text-3xl font-bold text-foreground">Сравнение API</h1>
          {unp && <p className="text-muted-foreground mt-2">УНП {unp}</p>}
        </div>

        {loading && <p className="text-muted-foreground">Загрузка...</p>}
        {error && (
          <Card className="border-destructive">
            <CardContent className="py-4 text-destructive">{error}</CardContent>
          </Card>
        )}

        {data && (
          <Card>
            <CardHeader>
              <CardTitle>Сравнение источников</CardTitle>
            </CardHeader>
            <CardContent>
              <pre className="text-sm overflow-x-auto whitespace-pre-wrap">
                {JSON.stringify(data, null, 2)}
              </pre>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
};

export default CompanyCompare;
