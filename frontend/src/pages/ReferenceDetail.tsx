import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { Header } from "@/components/layout/Header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { getReferenceData, searchReference, ReferenceItem } from "@/lib/api";

const ReferenceDetail = () => {
  const { type } = useParams();
  const [items, setItems] = useState<ReferenceItem[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadAll = useCallback(async () => {
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
  }, [type]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

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
    <div className="min-h-screen bg-background px-4 pb-12 pt-28">
      <Header />

      <div className="mx-auto max-w-5xl space-y-6">
        <div className="flex items-center justify-start">
          <Link to="/references">
            <Button variant="ghost" className="flex items-center gap-2">
              <ArrowLeft className="h-4 w-4" />
              К справочникам
            </Button>
          </Link>
        </div>

        <div className="space-y-2">
          <h1 className="text-3xl font-extrabold text-foreground sm:text-4xl">{type}</h1>
          <p className="max-w-2xl text-base leading-7 text-muted-foreground">
            Поиск по коду или названию. Карточки ниже подаются в более чистом и
            легком формате, чтобы с ними было проще работать.
          </p>
        </div>

        <form onSubmit={handleSearch} className="flex flex-col gap-3 sm:flex-row">
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
                <CardTitle className="text-xl">
                  {item.code} - {item.name}
                </CardTitle>
              </CardHeader>
              {item.extra && (
                <CardContent className="grid gap-3 md:grid-cols-2">
                  {Object.entries(item.extra).map(([key, value]) => (
                    <div key={key} className="rounded-[1.2rem] bg-background/40 px-4 py-3">
                      <span className="text-sm text-muted-foreground">{key}</span>
                      <div className="mt-1 text-foreground">{String(value ?? "")}</div>
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
