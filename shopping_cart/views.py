from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.http import HttpResponseRedirect, Http404
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from books.models import Book
from .models import Order, OrderItem, Payment
import stripe
import string
import random

stripe.api_key = settings.STRIPE_SECRET_KEY

def create_ref_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=15))

@login_required
def add_to_cart(request, book_slug):
    book = get_object_or_404(Book, slug=book_slug)
    order_item, created = OrderItem.objects.get_or_create(book=book)
    order, created = Order.objects.get_or_create(user=request.user, is_ordered=False)
    order.items.add(order_item)
    order.save()
    messages.info(request,"Item successfully added to your cart")
    return HttpResponseRedirect(request.META.get("HTTP_REFERER"))

@login_required
def remove_from_cart(request, book_slug):
    book = get_object_or_404(Book, slug=book_slug)
    order_item = get_object_or_404(OrderItem,book=book)
    order = get_object_or_404(Order, user=request.user, is_ordered=False)
    order.items.remove(order_item)
    order.save()
    messages.info(request,"Item successfully removed to your cart")
    return HttpResponseRedirect(request.META.get("HTTP_REFERER"))

@login_required
def order_view(request):
    order_qs = Order.objects.filter(user=request.user, is_ordered=False)
    if order_qs.exists():
        context = {
            'order': order_qs[0]
        }
        return render(request,'order_summary.html',context)
    return Http404

@login_required
def checkout(request):
    order_qs = Order.objects.filter(user=request.user, is_ordered=False)
    if order_qs.exists():
        order = order_qs[0]
    else:
        return Http404

    if request.method == 'POST':
        try:
            # Complete the order (ref code and set ordered to true)
            order.ref_code = create_ref_code()
            
            # Create stripe charge
            token = request.POST.get('stripeToken')
            charge = stripe.Charge.create(
            amount=int(order.get_total() * 100), # charge in cents, so convert dollar to cents 
            currency="sgd",
            source=token,
            description=f"Charge for {request.user.username}",
            )

            # Create payment object and link to order
            payment = Payment()
            payment.order = order
            payment.stripe_charge_id = charge.id
            payment.total_amount = order.get_total()
            payment.save()

            # Add the book to UserLibrary book list
            books = [item.book for item in order.items.all()]
            for book in books:
                request.user.userlibrary.books.add(book)
            order.is_ordered = True
            order.save()
            # Redirect to user account profile
            messages.success(request, "Your order was successful")
            return redirect('/accounts/profile/')
        except stripe.error.CardError as e:
            # Since it's a decline, stripe.error.CardError will be caught
            messages.error(request, "There was a card error")
            return redirect(reverse('cart:checkout'))
        except stripe.error.RateLimitError as e:
            # Too many requests made to the API too quickly
            messages.error(request, "There was a rate limit error on Stripe")
            return redirect(reverse('cart:checkout'))
        except stripe.error.InvalidRequestError as e:
            # Invalid parameters were supplied to Stripe's API
            messages.error(request, "Invalid parameter for Stripe request")
            return redirect(reverse('cart:checkout'))
        except stripe.error.AuthenticationError as e:
            # Authentication with Stripe's API failed
            # (maybe you changed API keys recently)
            messages.error(request, "Invalid Stripe API key")
            return redirect(reverse('cart:checkout'))
        except stripe.error.APIConnectionError as e:
            # Network communication with Stripe failed
            messages.error(request, "There was a network error")
            return redirect(reverse('cart:checkout'))
        except stripe.error.StripeError as e:
            # Display a very generic error to the user, and maybe send
            # yourself an email
            messages.error(request, "There was an error, please try again")
            return redirect(reverse('cart:checkout'))
        except Exception as e:
            # Something else happened, completely unrelated to Stripe
            messages.error(request, "There was a serious error. We're resolving the issue")
            return redirect(reverse('cart:checkout'))

    context = {
        'order':order
    }
    return render(request,'checkout.html',context)
