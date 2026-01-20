import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";

const NotFound = () => {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-6 bg-background px-4">
      <div className="text-center">
        <h1 className="text-3xl font-bold text-foreground">Страница не найдена</h1>
        <p className="text-muted-foreground mt-2">
          Проверьте адрес или вернитесь на главную страницу.
        </p>
      </div>
      <Link to="/">
        <Button>На главную</Button>
      </Link>
    </div>
  );
};

export default NotFound;
