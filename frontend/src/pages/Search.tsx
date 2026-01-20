import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { lookupCompanies } from "@/lib/api";

const Search = () => {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Array<{ unp: string; name: string }>>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = async (event: FormEvent) => {
    event.preventDefault();
    if (!query.trim()) {
      setResults([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await lookupCompanies(query.trim());
      setResults(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка поиска");
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background px-4 py-10">
      <div className="max-w-4xl mx-auto space-y-6">
        <div>
          <h1 className="text-3xl font-bold text-foreground">Поиск компаний</h1>
          <p className="text-muted-foreground mt-2">
            Введите УНП или часть названия компании.
          </p>
        </div>

        <form onSubmit={handleSearch} className="flex gap-3">
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="УНП или название"
          />
          <Button type="submit" disabled={loading}>
            {loading ? "Ищем..." : "Поиск"}
          </Button>
        </form>

        {error && (
          <Card className="border-destructive">
            <CardContent className="py-4 text-destructive">{error}</CardContent>
          </Card>
        )}

        <div className="space-y-4">
          {results.map((item) => (
            <Card key={item.unp}>
              <CardHeader>
                <CardTitle className="text-lg">
                  {item.name} (УНП {item.unp})
                </CardTitle>
              </CardHeader>
              <CardContent>
                <Link to={`/company/${item.unp}`}>
                  <Button variant="outline">Открыть профиль</Button>
                </Link>
              </CardContent>
            </Card>
          ))}
          {!loading && results.length === 0 && query.trim() && (
            <p className="text-muted-foreground">Ничего не найдено.</p>
          )}
        </div>
      </div>
    </div>
  );
};

export default Search;
