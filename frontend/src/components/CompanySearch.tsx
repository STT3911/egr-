import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Search, ArrowRight, Building2, Loader2 } from "lucide-react";
import { lookupCompanies, CompanyLookupResult } from "@/lib/api";
import { motion, AnimatePresence } from "framer-motion";

interface CompanySearchProps {
  variant?: "hero" | "compact";
  placeholder?: string;
  onSearchStart?: () => void;
}

export const CompanySearch = ({ 
  variant = "compact",
  placeholder = "Введите УНП или название компании",
  onSearchStart
}: CompanySearchProps) => {
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<CompanyLookupResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const navigate = useNavigate();
  const searchRef = useRef<HTMLDivElement>(null);

  // Закрытие подсказок при клике вне компонента
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(event.target as Node)) {
        setShowSuggestions(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Автодополнение с debounce
  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setSuggestions([]);
      setShowSuggestions(false);
      setLoading(false);
      return;
    }

    setLoading(true);
    const timer = setTimeout(async () => {
      try {
        const data = await lookupCompanies(trimmed);
        console.log("Получены подсказки:", data.results.length, data.results);
        setSuggestions(data.results);
        setShowSuggestions(data.results.length > 0);
      } catch (err) {
        console.error("Ошибка автодополнения:", err);
        setSuggestions([]);
        setShowSuggestions(false);
      } finally {
        setLoading(false);
      }
    }, 300);

    return () => {
      clearTimeout(timer);
      setLoading(false);
    };
  }, [query]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;

    onSearchStart?.();

    // Если введен полный УНП (9 цифр) - сразу переход
    if (/^\d{9}$/.test(trimmed)) {
      navigate(`/company/${trimmed}`);
      setShowSuggestions(false);
      return;
    }

    // Если есть только одна подсказка - переход к ней
    if (suggestions.length === 1) {
      navigate(`/company/${suggestions[0].unp}`);
      setShowSuggestions(false);
      return;
    }

    // Иначе показываем подсказки
    setShowSuggestions(true);
  };

  const handleSelectCompany = (unp: number) => {
    navigate(`/company/${unp}`);
    setShowSuggestions(false);
    setQuery("");
  };

  const isHero = variant === "hero";

  return (
    <div ref={searchRef} className="relative w-full">
      <form onSubmit={handleSearch} className={isHero ? "max-w-2xl mx-auto" : "w-full"}>
        <div className={`relative flex items-center gap-3 ${
          isHero 
            ? "p-2 bg-card rounded-2xl shadow-card border border-border" 
            : "p-1 bg-card rounded-lg border border-border"
        }`}>
          <div className="flex-1 flex items-center gap-3 pl-4">
            <Search className={`${isHero ? 'w-5 h-5' : 'w-4 h-4'} text-muted-foreground flex-shrink-0`} />
            <Input
              type="text"
              placeholder={placeholder}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onFocus={() => suggestions.length > 0 && setShowSuggestions(true)}
              className={`border-0 bg-transparent focus-visible:ring-0 focus-visible:ring-offset-0 placeholder:text-muted-foreground/60 ${
                isHero ? 'text-base sm:text-lg' : 'text-sm'
              }`}
            />
            {loading && <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />}
          </div>
          <Button 
            type="submit"
            size={isHero ? "lg" : "default"}
            className={`gradient-primary text-primary-foreground shadow-soft hover:shadow-glow transition-all ${
              isHero ? 'px-6 sm:px-8' : 'px-4'
            }`}
          >
            {isHero ? (
              <>
                <span className="hidden sm:inline">Найти</span>
                <ArrowRight className="w-5 h-5 sm:ml-2" />
              </>
            ) : (
              <Search className="w-4 h-4" />
            )}
          </Button>
        </div>
      </form>

      {/* Dropdown с подсказками */}
      {showSuggestions && suggestions.length > 0 && (
        <div
          style={{ zIndex: 9999 }}
          className={`absolute top-full mt-2 w-full min-w-full bg-card rounded-lg shadow-xl border border-border ${
            isHero ? 'max-w-2xl mx-auto left-0 right-0' : ''
          }`}
        >
          <div 
            className="custom-scrollbar" 
            style={{ 
              maxHeight: '300px',
              overflowY: 'scroll',
              overflowX: 'hidden',
              WebkitOverflowScrolling: 'touch'
            }}
          >
              {suggestions.map((item, index) => (
                <button
                  key={item.unp}
                  onClick={() => handleSelectCompany(item.unp)}
                  className="w-full px-4 py-3 flex items-center gap-3 hover:bg-accent/50 transition-colors border-b border-border last:border-0 text-left group"
                >
                  <div className="flex-shrink-0">
                    <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center group-hover:bg-primary/20 transition-colors">
                      <Building2 className="w-5 h-5 text-primary" />
                    </div>
                  </div>
                  <div className="flex-1 min-w-0 overflow-hidden">
                    <div 
                      className="font-medium text-foreground text-sm truncate mb-1"
                      title={item.full_name_ru || item.short_name_ru || item.name || ""}
                    >
                      {item.full_name_ru || item.short_name_ru || item.name}
                    </div>
                    <div className="text-xs text-muted-foreground font-mono whitespace-nowrap">
                      УНП: {item.unp}
                    </div>
                  </div>
                  <div className="flex-shrink-0 ml-2">
                    <ArrowRight className="w-4 h-4 text-muted-foreground group-hover:text-primary group-hover:translate-x-1 transition-all" />
                  </div>
                </button>
              ))}
            </div>
          {suggestions.length >= 10 && (
            <div className="px-4 py-2 bg-muted/30 text-xs text-muted-foreground text-center border-t border-border">
              Показаны первые {suggestions.length} результатов. Уточните запрос для более точного поиска.
            </div>
          )}
        </div>
      )}
    </div>
  );
};
