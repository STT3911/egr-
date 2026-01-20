import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CompanyLookupResult, lookupCompanies } from "@/lib/api";

const Search = () => {
  const [query, setQuery] = useState("");
  const navigate = useNavigate();
  const [suggestions, setSuggestions] = useState<CompanyLookupResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = async (event: FormEvent) => {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;
    setLoading(true);
    setError(null);
    try {
      if (/^\d{9}$/.test(trimmed)) {
        navigate(`/company/${trimmed}`);
        return;
      }
      if (suggestions.length === 1) {
        navigate(`/company/${suggestions[0].unp}`);
        return;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка поиска");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setSuggestions([]);
      return;
    }
    setSuggesting(true);
    const timer = setTimeout(async () => {
      try {
        const data = await lookupCompanies(trimmed);
        setSuggestions(data.results);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Ошибка подсказок");
        setSuggestions([]);
      } finally {
        setSuggesting(false);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [query]);

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
        {query.trim().length >= 2 && query.trim().match(/^\d+$/) && suggestions[0] && (
          <p className="text-sm text-muted-foreground">
            Найдена организация:{" "}
            <Link
              to={`/company/${suggestions[0].unp}`}
              className="text-primary hover:underline"
            >
              {suggestions[0].name} (УНП {suggestions[0].unp})
            </Link>
          </p>
        )}

        {error && (
          <Card className="border-destructive">
            <CardContent className="py-4 text-destructive">{error}</CardContent>
          </Card>
        )}

        <div className="space-y-4">
          {suggestions.map((item) => (
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
          {!suggesting && suggestions.length === 0 && query.trim().length >= 2 && (
            <p className="text-muted-foreground">Ничего не найдено.</p>
          )}
        </div>
      </div>
    </div>
  );
};

export default Search;
