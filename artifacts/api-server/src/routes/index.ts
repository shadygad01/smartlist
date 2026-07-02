import { Router, type IRouter } from "express";
import healthRouter from "./health";
import storageRouter from "./storage";
import portfolioRouter from "./portfolio";

const router: IRouter = Router();

router.use(healthRouter);
router.use(storageRouter);
router.use(portfolioRouter);

export default router;
