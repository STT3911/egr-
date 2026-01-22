import { FormEvent, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ArrowLeft } from "lucide-react";
import { getReferenceData, searchReference, ReferenceItem } from "@/lib/api";

const ReferenceDetail = () => {
  const { type } = useParams();
  const [items, setItems] = useState<ReferenceItem[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadAll = async () => {
    if (!type) return;
    setLoading(true);
    setError(null);
    try {
      const data = await getReferenceData(type);
      setItems(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка загрузки данных");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAll();
  }, [type]);

  const handleSearch = async (event: FormEvent) => {
    event.preventDefault();
    if (!type) return;
    if (!query.trim()) {
      loadAll();
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await searchReference(type, query.trim());
      setItems(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка поиска");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background px-4 py-10">
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Back to Home Button */}
        <div className="flex items-center justify-start">
          <Link to="/">
            <Button variant="ghost" className="flex items-center gap-2 glass hover:bg-primary/10 dark:hover:bg-primary/20 transition-all duration-300">
              <ArrowLeft className="w-4 h-4" />
              На главную
            </Button>
          </Link>
        </div>

        <div>
          <h1 className="text-3xl font-bold text-foreground">{type}</h1>
          <p className="text-muted-foreground mt-2">
            Данные справочника. Можно искать по коду или названию.
          </p>
        </div>

        <form onSubmit={handleSearch} className="flex gap-3">
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Код или название"
          />
          <Button type="submit" disabled={loading}>
            Поиск
          </Button>
        </form>

        {loading && <p className="text-muted-foreground">Загрузка...</p>}
        {error && (
          <Card className="border-destructive">
            <CardContent className="py-4 text-destructive">{error}</CardContent>
          </Card>
        )}

        <div className="space-y-3">
          {items.map((item) => (
            <Card key={`${item.code}`}>
              <CardHeader>
                <CardTitle className="text-lg">
                  {item.code} — {item.name}
                </CardTitle>
              </CardHeader>
              {item.extra && (
                <CardContent className="grid gap-2 md:grid-cols-2">
                  {Object.entries(item.extra).map(([key, value]) => (
                    <div key={key}>
                      <span className="text-sm text-muted-foreground">{key}</span>
                      <div className="text-foreground">{String(value ?? "")}</div>
                    </div>
                  ))}
                </CardContent>
              )}
            </Card>
          ))}
          {!loading && items.length === 0 && (
            <p className="text-muted-foreground">Нет данных для отображения.</p>
          )}
        </div>
      </div>
    </div>
  );
};

export default ReferenceDetail;
