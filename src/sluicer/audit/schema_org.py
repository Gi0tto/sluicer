"""schema.org's type tree and enumerations, as far as the audit needs them.

Two facts the audit cannot get from a page: which types sit below a type Google
names -- a ``Restaurant`` is a ``LocalBusiness`` -- and which terms an
enumeration holds -- ``InStock`` is an ``ItemAvailability``. Both are read from
schema.org's own export of its vocabulary,
https://schema.org/version/latest/schemaorg-current-https-types.csv, release
30.1, on 2026-09-23: a type's subtypes are every type whose ``subTypeOf``
reaches it, transitively, leaving out the types schema.org marks
``supersededBy``; an enumeration's terms are the rows whose ``enumerationtype``
names it, superseded ones left out likewise. Only the roots and enumerations
the audit asks about are kept.

schema.org publishes its vocabulary under CC BY-SA 3.0; these are its type and
term names, which every page using the vocabulary writes, and their source is
named here.
"""

from __future__ import annotations


def _names(text: str) -> frozenset[str]:
    return frozenset(text.split())


# Every type below each root, the root itself left out. A root with no subtype
# (Movie, MusicRecording, Recipe) has no entry.
SUBTYPES: dict[str, frozenset[str]] = {
    "Article": _names(
        "APIReference AdvertiserContentArticle AnalysisNewsArticle"
        " AskPublicNewsArticle BackgroundNewsArticle BlogPosting"
        " DiscussionForumPosting LiveBlogPosting MedicalScholarlyArticle NewsArticle"
        " OpinionNewsArticle Report ReportageNewsArticle ReviewNewsArticle"
        " SatiricalArticle ScholarlyArticle SocialMediaPosting TechArticle"
    ),
    "Book": _names("Audiobook SequentialArt"),
    "CreativeWorkSeason": _names("PodcastSeason RadioSeason TVSeason"),
    "CreativeWorkSeries": _names(
        "BookSeries ComicSeries MovieSeries Newspaper Periodical PodcastSeries"
        " RadioSeries TVSeries VideoGameSeries"
    ),
    "Episode": _names("PodcastEpisode RadioEpisode TVEpisode"),
    "Event": _names(
        "BroadcastEvent BusinessEvent ChildrensEvent ComedyEvent ConferenceEvent"
        " CourseInstance DanceEvent DeliveryEvent EducationEvent EventSeries"
        " ExhibitionEvent Festival FoodEvent Hackathon LiteraryEvent MusicEvent"
        " OnDemandEvent PerformingArtsEvent PublicationEvent SaleEvent"
        " ScreeningEvent SocialEvent SportsEvent TheaterEvent VisualArtsEvent"
    ),
    "FoodEstablishment": _names(
        "Bakery BarOrPub Brewery CafeOrCoffeeShop Distillery FastFoodRestaurant"
        " IceCreamShop Restaurant Winery"
    ),
    "Game": _names("VideoGame"),
    "LocalBusiness": _names(
        "AccountingService AdultEntertainment AmusementPark AnimalShelter"
        " ArchiveOrganization ArtGallery Attorney Audiology AutoBodyShop AutoDealer"
        " AutoPartsStore AutoRental AutoRepair AutoWash AutomatedTeller"
        " AutomotiveBusiness Bakery BankOrCreditUnion BarOrPub BeautySalon"
        " BedAndBreakfast BikeStore BookStore BowlingAlley Brewery CafeOrCoffeeShop"
        " Campground Casino ChildCare ClothingStore ComedyClub CommunityHealth"
        " ComputerStore ConvenienceStore CovidTestingFacility DaySpa Dentist"
        " DepartmentStore Dermatology DietNutrition Distillery DryCleaningOrLaundry"
        " Electrician ElectronicsStore Emergency EmergencyService EmploymentAgency"
        " EntertainmentBusiness ExerciseGym FastFoodRestaurant FinancialService"
        " FireStation Florist FoodEstablishment FurnitureStore GardenStore"
        " GasStation GeneralContractor Geriatric GolfCourse GovernmentOffice"
        " GroceryStore Gynecologic HVACBusiness HairSalon HardwareStore"
        " HealthAndBeautyBusiness HealthClub HobbyShop HomeAndConstructionBusiness"
        " HomeGoodsStore Hospital Hostel Hotel HousePainter IceCreamShop"
        " IndividualPhysician InsuranceAgency InternetCafe JewelryStore LegalService"
        " Library LiquorStore Locksmith LodgingBusiness MedicalBusiness"
        " MedicalClinic MensClothingStore Midwifery MobilePhoneStore Motel"
        " MotorcycleDealer MotorcycleRepair MovieRentalStore MovieTheater"
        " MovingCompany MusicStore NailSalon NightClub Notary Nursing Obstetric"
        " OfficeEquipmentStore Oncologic Ophthalmology Optician Optometric"
        " Otolaryngologic OutletStore PawnShop Pediatric PetStore Pharmacy Physician"
        " PhysiciansOffice Physiotherapy PlasticSurgery Plumber Podiatric"
        " PoliceStation PostOffice PrimaryCare ProfessionalService Psychiatric"
        " PublicHealth PublicSwimmingPool RadioStation RealEstateAgent"
        " RecyclingCenter Resort Restaurant RoofingContractor SelfStorage ShoeStore"
        " ShoppingCenter SkiResort SportingGoodsStore SportsActivityLocation"
        " SportsClub StadiumOrArena Store TattooParlor TelevisionStation"
        " TennisComplex TireShop TouristInformationCenter ToyStore TravelAgency"
        " VacationRental WholesaleStore Winery"
    ),
    "MediaObject": _names(
        "3DModel AmpStory AudioObject AudioObjectSnapshot Audiobook Barcode"
        " DataDownload ImageObject ImageObjectSnapshot LegislationObject"
        " MusicVideoObject TextObject VideoObject VideoObjectSnapshot"
    ),
    "MusicPlaylist": _names("MusicAlbum MusicRelease"),
    "Offer": _names("AggregateOffer OfferForLease OfferForPurchase"),
    "Organization": _names(
        "AccountingService AdultEntertainment Airline AmusementPark AnimalShelter"
        " ArchiveOrganization ArtGallery Attorney Audiology AutoBodyShop AutoDealer"
        " AutoPartsStore AutoRental AutoRepair AutoWash AutomatedTeller"
        " AutomotiveBusiness Bakery BankOrCreditUnion BarOrPub BeautySalon"
        " BedAndBreakfast BikeStore BookStore BowlingAlley Brewery CafeOrCoffeeShop"
        " Campground Casino ChildCare ClothingStore CollegeOrUniversity ComedyClub"
        " CommunityHealth ComputerStore Consortium ConvenienceStore Cooperative"
        " Corporation CovidTestingFacility DanceGroup DaySpa Dentist DepartmentStore"
        " Dermatology DiagnosticLab DietNutrition Distillery DryCleaningOrLaundry"
        " EducationalOrganization Electrician ElectronicsStore ElementarySchool"
        " Emergency EmergencyService EmploymentAgency EntertainmentBusiness"
        " ExerciseGym FastFoodRestaurant FinancialService FireStation Florist"
        " FoodEstablishment FundingAgency FundingScheme FurnitureStore GardenStore"
        " GasStation GeneralContractor Geriatric GolfCourse GovernmentOffice"
        " GovernmentOrganization GroceryStore Gynecologic HVACBusiness HairSalon"
        " HardwareStore HealthAndBeautyBusiness HealthClub HighSchool HobbyShop"
        " HomeAndConstructionBusiness HomeGoodsStore Hospital Hostel Hotel"
        " HousePainter IceCreamShop IndividualPhysician InsuranceAgency InternetCafe"
        " JewelryStore LegalService Library LibrarySystem LiquorStore LocalBusiness"
        " Locksmith LodgingBusiness MedicalBusiness MedicalClinic"
        " MedicalOrganization MensClothingStore MiddleSchool Midwifery"
        " MobilePhoneStore Motel MotorcycleDealer MotorcycleRepair MovieRentalStore"
        " MovieTheater MovingCompany MusicGroup MusicStore NGO NailSalon"
        " NewsMediaOrganization NightClub Notary Nursing Obstetric"
        " OfficeEquipmentStore Oncologic OnlineBusiness OnlineMarketplace"
        " OnlineStore Ophthalmology Optician Optometric Otolaryngologic OutletStore"
        " PawnShop Pediatric PerformingGroup PetStore Pharmacy Physician"
        " PhysiciansOffice Physiotherapy PlasticSurgery Plumber Podiatric"
        " PoliceStation PoliticalParty PostOffice Preschool PrimaryCare"
        " ProfessionalService Project Psychiatric PublicHealth PublicSwimmingPool"
        " RadioStation RealEstateAgent RecyclingCenter ResearchOrganization"
        " ResearchProject Resort Restaurant RoofingContractor School"
        " SearchRescueOrganization SelfStorage ShoeStore ShoppingCenter SkiResort"
        " SportingGoodsStore SportsActivityLocation SportsClub SportsOrganization"
        " SportsTeam StadiumOrArena Store TattooParlor TelevisionStation"
        " TennisComplex TheaterGroup TireShop TouristInformationCenter ToyStore"
        " TravelAgency VacationRental VeterinaryCare WholesaleStore Winery"
        " WorkersUnion"
    ),
    "Product": _names(
        "BusOrCoach Car DietarySupplement Drug IndividualProduct Motorcycle"
        " MotorizedBicycle ProductCollection ProductGroup ProductModel SomeProducts"
        " Vehicle"
    ),
    "SoftwareApplication": _names(
        "MobileApplication OperatingSystem RuntimePlatform VideoGame WebApplication"
    ),
    "Vehicle": _names("BusOrCoach Car Motorcycle MotorizedBicycle"),
    "VideoObject": _names("VideoObjectSnapshot"),
}

# The terms of each enumeration, written as pages write them without the
# vocabulary's address: ``InStock`` for ``https://schema.org/InStock``.
ENUMERATIONS: dict[str, frozenset[str]] = {
    "BookFormatType": _names(
        "AudiobookFormat EBook GraphicNovel Hardcover Pamphlet Paperback"
    ),
    "DayOfWeek": _names(
        "Friday Monday PublicHolidays Saturday Sunday Thursday Tuesday Wednesday"
    ),
    "EventAttendanceModeEnumeration": _names(
        "MixedEventAttendanceMode OfflineEventAttendanceMode OnlineEventAttendanceMode"
    ),
    "EventStatusType": _names(
        "EventCancelled EventMovedOnline EventPostponed EventRescheduled EventScheduled"
    ),
    "ItemAvailability": _names(
        "BackOrder Discontinued InStock InStoreOnly LimitedAvailability MadeToOrder"
        " OnlineOnly OutOfStock PreOrder PreSale Reserved SoldOut"
    ),
    "MerchantReturnEnumeration": _names(
        "MerchantReturnFiniteReturnWindow MerchantReturnNotPermitted"
        " MerchantReturnUnlimitedWindow MerchantReturnUnspecified"
    ),
    "OfferItemCondition": _names(
        "DamagedCondition NewCondition RefurbishedCondition UsedCondition"
    ),
    "ReturnFeesEnumeration": _names(
        "FreeReturn OriginalShippingFees RestockingFees"
        " ReturnFeesCustomerResponsibility ReturnShippingFees"
    ),
    "ReturnMethodEnumeration": _names(
        "KeepProduct ReturnAtKiosk ReturnByMail ReturnInStore"
    ),
}


def below(root: str) -> frozenset[str]:
    """The schema.org types below ``root``, or none when it has none listed here."""
    return SUBTYPES.get(root, frozenset())
