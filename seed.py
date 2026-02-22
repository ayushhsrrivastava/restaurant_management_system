from app import app, db, Product, Order, OrderItem, Table
from datetime import datetime, timedelta
import random

def seed_data():
    with app.app_context():
        # Clear existing data to start fresh
        db.drop_all()
        db.create_all()

        print("Seeding Products...")
        products = [
            Product(name="Margherita Pizza", price=12.0, cost=4.5),
            Product(name="Cheeseburger", price=10.5, cost=3.8),
            Product(name="Caesar Salad", price=8.0, cost=2.2),
            Product(name="Pasta Carbonara", price=14.0, cost=5.0),
            Product(name="Iced Latte", price=4.5, cost=1.1),
            Product(name="Chocolate Brownie", price=6.0, cost=1.5)
        ]
        db.session.add_all(products)
        db.session.commit()

        print("Seeding Tables...")
        for i in range(1, 6):
            db.session.add(Table(table_number=i))
        db.session.commit()

        print("Seeding Historical Orders for Analytics...")
        # Create orders over the last 30 days
        for i in range(50):
            days_ago = random.randint(0, 30)
            order_date = datetime.utcnow() - timedelta(days=days_ago)
            
            # Randomly pick 1-3 products
            order_items_count = random.randint(1, 3)
            selected_products = random.sample(products, order_items_count)
            
            rev = 0
            prof = 0
            
            new_order = Order(
                table_id=random.randint(1, 5),
                order_type=random.choice(['dine-in', 'takeaway']),
                created_at=order_date
            )
            db.session.add(new_order)
            db.session.flush()

            for p in selected_products:
                qty = random.randint(1, 2)
                rev += p.price * qty
                prof += (p.price - p.cost) * qty
                
                item = OrderItem(
                    order_id=new_order.id,
                    product_id=p.id,
                    quantity=qty,
                    price_at_time=p.price,
                    profit_at_time=(p.price - p.cost)
                )
                db.session.add(item)

            new_order.total_revenue = rev
            new_order.total_profit = prof

        db.session.commit()
        print("Database seeded successfully!")

if __name__ == "__main__":
    seed_data()