import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
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
    <div className="min-h-screen bg-background px-4 py-10">
      <div className="max-w-4xl mx-auto space-y-6">
        <div>
          <h1 className="text-3xl font-bold text-foreground">Справочники ЕГР</h1>
          <p className="text-muted-foreground mt-2">
            Выберите справочник для просмотра данных.
          </p>
        </div>

        {loading && <p className="text-muted-foreground">Загрузка...</p>}
        {error && (
          <Card className="border-destructive">
            <CardContent className="py-4 text-destructive">{error}</CardContent>
          </Card>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          {types.map((type) => (
            <Card key={type}>
              <CardHeader>
                <CardTitle className="text-lg">{type}</CardTitle>
              </CardHeader>
              <CardContent>
                <Link
                  to={`/references/${encodeURIComponent(type)}`}
                  className="text-primary hover:underline"
                >
                  Открыть справочник
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
