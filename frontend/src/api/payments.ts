import type { PaymentRecord } from "../types/payment";
import { api } from "./client";

export const listPayments = () => api.get<PaymentRecord[]>("/payments/");

export const listMyPayments = () => api.get<PaymentRecord[]>("/my-payments/");
