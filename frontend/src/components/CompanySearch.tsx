import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowRight, Building2, Loader2, Mail, MapPin, Phone, Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { lookupCompanies, CompanyLookupResult } from "@/lib/api";

interface CompanySearchProps {
  variant?: "hero" | "compact";
  placeholder?: string;
  onSearchStart?: () => void;
}

export const CompanySearch = ({
  variant = "compact",
  placeholder = "УНП, название, телефон, email или адрес",
  onSearchStart,
}: CompanySearchProps) => {
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<CompanyLookupResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [focused, setFocused] = useState(false);
  const [dropdownDirection, setDropdownDirection] = useState<"down" | "up">("down");
  const navigate = useNavigate();
  const searchRef = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const MAX_SUGGESTIONS = 5;

  useEffect(() => {
    if (showSuggestions && dropdownRef.current && searchRef.current) {
      const searchRect = searchRef.current.getBoundingClientRect();
      const dropdownHeight = dropdownRef.current.offsetHeight;
      const spaceBelow = window.innerHeight - searchRect.bottom;
      const spaceAbove = searchRect.top;

      if (spaceBelow < dropdownHeight && spaceAbove > spaceBelow) {
        setDropdownDirection("up");
      } else {
        setDropdownDirection("down");
      }
    }
  }, [showSuggestions, suggestions]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(event.target as Node)) {
        setShowSuggestions(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

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
        setSuggestions(data.results);
        setShowSuggestions(data.results.length > 0);
      } catch (err) {
        console.error("Autocomplete error:", err);
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

  const handleSearch = (event: React.FormEvent) => {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;

    onSearchStart?.();

    if (/^\d{9}$/.test(trimmed)) {
      navigate(`/company/${trimmed}`);
      setShowSuggestions(false);
      return;
    }

    if (suggestions.length === 1) {
      navigate(`/company/${suggestions[0].unp}`);
      setShowSuggestions(false);
      return;
    }

    if (suggestions.length > 0) {
      setShowSuggestions(true);
    }
  };

  const handleSelectCompany = (unp: number) => {
    navigate(`/company/${unp}`);
    setShowSuggestions(false);
    setQuery("");
  };

  const handleInputFocus = () => {
    setFocused(true);
    if (suggestions.length > 0) {
      setShowSuggestions(true);
    }
  };

  const isHero = variant === "hero";

  return (
    <div ref={searchRef} className="relative w-full">
      <form onSubmit={handleSearch} className={isHero ? "mx-auto max-w-2xl" : "w-full"}>
        <motion.div
          animate={{
            scale: focused && isHero ? 1.015 : 1,
            boxShadow: focused
              ? "0 30px 80px -36px hsl(var(--primary) / 0.45)"
              : "0 18px 50px -32px hsl(var(--foreground) / 0.24)",
          }}
          transition={{ duration: 0.25 }}
          className={`relative flex items-center gap-3 overflow-hidden ${
            isHero
              ? "surface-card rounded-[1.7rem] border border-border/80 p-2.5"
              : "surface-card rounded-[1.35rem] border border-border/80 p-1.5"
          }`}
        >
          <motion.div
            className="pointer-events-none absolute inset-y-0 left-0 w-32 bg-gradient-to-r from-transparent via-primary/12 to-transparent"
            animate={{ x: focused ? ["-120%", "760%"] : "-120%" }}
            transition={{ duration: 1.2, ease: "easeInOut" }}
          />

          <div className="flex flex-1 items-center gap-3 pl-4">
            <motion.span
              animate={{ rotate: loading ? 12 : 0, scale: focused ? 1.08 : 1 }}
              transition={{ duration: 0.2 }}
              className="flex"
            >
              <Search className={`${isHero ? "h-5 w-5" : "h-4 w-4"} flex-shrink-0 text-primary`} />
            </motion.span>

            <Input
              type="text"
              placeholder={placeholder}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onFocus={handleInputFocus}
              onBlur={() => setFocused(false)}
              className={`h-auto border-0 bg-transparent px-0 py-0 focus-visible:ring-0 focus-visible:ring-offset-0 placeholder:text-muted-foreground/60 ${
                isHero ? "text-base sm:text-lg" : "text-sm"
              }`}
            />

            {loading && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
          </div>

          <Button
            type="submit"
            size={isHero ? "lg" : "default"}
            className={isHero ? "px-6 sm:px-8" : "px-4"}
          >
            {isHero ? (
              <>
                <span className="hidden sm:inline">Найти</span>
                <ArrowRight className="h-5 w-5 sm:ml-2" />
              </>
            ) : (
              <Search className="h-4 w-4" />
            )}
          </Button>
        </motion.div>
      </form>

      <AnimatePresence>
        {showSuggestions && suggestions.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: dropdownDirection === "down" ? -10 : 10, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: dropdownDirection === "down" ? -10 : 10, scale: 0.95 }}
            transition={{ duration: 0.2 }}
            ref={dropdownRef}
            style={{ zIndex: 9999 }}
            className={`absolute ${
              dropdownDirection === "down" ? "top-full mt-2" : "bottom-full mb-2"
            } surface-card w-full min-w-full rounded-[1.35rem] border border-border/80 shadow-card ${
              isHero ? "left-0 right-0 mx-auto max-w-2xl" : ""
            }`}
          >
            <div className="custom-scrollbar max-h-[400px] overflow-y-auto">
              {suggestions.slice(0, MAX_SUGGESTIONS).map((item, index) => (
                <motion.button
                  key={item.unp}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.18, delay: index * 0.035 }}
                  onClick={() => handleSelectCompany(item.unp)}
                  className="group flex w-full items-center gap-3 border-b border-border/60 px-4 py-3 text-left transition-colors hover:bg-foreground/[0.03] last:border-0"
                >
                  <div className="flex-shrink-0">
                    <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 transition-colors group-hover:bg-primary/18">
                      <Building2 className="h-5 w-5 text-primary" />
                    </div>
                  </div>

                  <div className="min-w-0 flex-1 overflow-hidden">
                    <div
                      className="mb-1 truncate text-sm font-medium text-foreground"
                      title={item.full_name_ru || item.short_name_ru || item.name || ""}
                    >
                      {item.full_name_ru || item.short_name_ru || item.name}
                    </div>

                    {item.matched_historical_name && item.matched_name && (
                      <div
                        className="mb-1 truncate text-xs text-accent"
                        title={`Историческое название: ${item.matched_name}`}
                      >
                        Историческое название: {item.matched_name}
                      </div>
                    )}

                    {item.matched_type && item.matched_value && (
                      <div className="mb-1 flex items-center gap-1.5 truncate text-xs text-primary">
                        {item.matched_type === "phone" && <Phone className="h-3 w-3 flex-shrink-0" />}
                        {item.matched_type === "email" && <Mail className="h-3 w-3 flex-shrink-0" />}
                        {item.matched_type === "address" && <MapPin className="h-3 w-3 flex-shrink-0" />}
                        <span className="truncate" title={item.matched_value}>
                          {item.matched_value}
                        </span>
                      </div>
                    )}

                    <div className="font-mono text-xs whitespace-nowrap text-muted-foreground">
                      УНП: {item.unp}
                    </div>
                  </div>

                  <div className="ml-2 flex-shrink-0">
                    <ArrowRight className="h-4 w-4 text-muted-foreground transition-all group-hover:translate-x-1 group-hover:text-primary" />
                  </div>
                </motion.button>
              ))}
            </div>

            {suggestions.length > MAX_SUGGESTIONS && (
              <div className="border-t border-border/60 bg-muted/30 px-4 py-2 text-center text-xs text-muted-foreground">
                Показаны первые {MAX_SUGGESTIONS} из {suggestions.length} результатов. Уточните
                запрос для более точного поиска.
              </div>
            )}

            <div
              className={`absolute ${
                dropdownDirection === "down"
                  ? "-top-2 left-4 -translate-x-1/2"
                  : "-bottom-2 left-4 -translate-x-1/2 rotate-180"
              } h-4 w-4 overflow-hidden`}
            >
              <div className="h-4 w-4 translate-y-1/2 rotate-45 border-l border-t border-border/80 bg-card" />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
