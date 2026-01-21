import { CompanySearch } from "@/components/CompanySearch";
import { Card, CardContent } from "@/components/ui/card";
import { Building2, Search as SearchIcon, TrendingUp } from "lucide-react";

const Search = () => {
  return (
    <div className="min-h-screen bg-background px-4 py-10">
      <div className="max-w-4xl mx-auto space-y-8">
        {/* Header */}
        <div className="text-center space-y-3">
          <h1 className="text-4xl font-bold text-foreground">Поиск компаний</h1>
          <p className="text-lg text-muted-foreground">
            Введите УНП или часть названия компании для поиска
          </p>
        </div>

        {/* Search Box */}
        <div className="max-w-2xl mx-auto">
          <CompanySearch 
            variant="compact"
            placeholder="Поиск по УНП или названию..."
          />
        </div>

        {/* Info Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-6">
          <Card className="p-6 hover:shadow-lg transition-shadow">
            <div className="flex items-start gap-4">
              <div className="p-3 rounded-lg bg-primary/10">
                <Building2 className="w-6 h-6 text-primary" />
              </div>
              <div>
                <h3 className="font-semibold text-foreground mb-1">500K+ компаний</h3>
                <p className="text-sm text-muted-foreground">
                  Полный реестр ЮЛ и ИП Республики Беларусь
                </p>
              </div>
            </div>
          </Card>

          <Card className="p-6 hover:shadow-lg transition-shadow">
            <div className="flex items-start gap-4">
              <div className="p-3 rounded-lg bg-primary/10">
                <SearchIcon className="w-6 h-6 text-primary" />
              </div>
              <div>
                <h3 className="font-semibold text-foreground mb-1">Быстрый поиск</h3>
                <p className="text-sm text-muted-foreground">
                  Автодополнение и мгновенные подсказки
                </p>
              </div>
            </div>
          </Card>

          <Card className="p-6 hover:shadow-lg transition-shadow">
            <div className="flex items-start gap-4">
              <div className="p-3 rounded-lg bg-primary/10">
                <TrendingUp className="w-6 h-6 text-primary" />
              </div>
              <div>
                <h3 className="font-semibold text-foreground mb-1">Актуальные данные</h3>
                <p className="text-sm text-muted-foreground">
                  Информация обновляется в реальном времени
                </p>
              </div>
            </div>
          </Card>
        </div>

        {/* Hints */}
        <Card className="p-6 bg-primary/5 border-primary/20">
          <h3 className="font-semibold text-foreground mb-3">Советы по поиску:</h3>
          <ul className="space-y-2 text-sm text-muted-foreground">
            <li className="flex items-start gap-2">
              <span className="text-primary mt-0.5">•</span>
              <span>Введите полный УНП (9 цифр) для моментального перехода к профилю компании</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-primary mt-0.5">•</span>
              <span>Начните вводить название компании для появления подсказок</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-primary mt-0.5">•</span>
              <span>Используйте первые цифры УНП для поиска похожих компаний</span>
            </li>
          </ul>
        </Card>
      </div>
    </div>
  );
};

export default Search;
